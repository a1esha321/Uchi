"""
smart_solver.py — решает тесты разных типов через Groq.
"""

import os
import json
import re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()


class SmartSolver:
    def __init__(self, lecture_knowledge: str = ""):
        self.knowledge = lecture_knowledge[:25000] if lecture_knowledge else ""
        self._client = None

    @property
    def client(self):
        if self._client is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY не задан")
            self._client = Groq(api_key=api_key)
        return self._client

    def solve_question(self, question: dict) -> tuple:
        """
        Универсальное решение вопроса.
        Возвращает (answer, confidence), где answer:
        - int (индекс) для radio/checkbox
        - str для shortanswer/essay
        """
        qtype = question.get("type", "radio")
        qtext = question.get("question", "")
        options = question.get("options", [])

        if qtype in ("shortanswer", "essay"):
            return self._solve_text(qtext, qtype)
        else:
            return self._solve_choice(qtext, options)

    def _solve_choice(self, question: str, options: list) -> tuple:
        """Решает вопрос с выбором варианта."""
        if not options:
            return 0, 0.0

        opts = "\n".join([f"{i+1}. {o}" for i, o in enumerate(options)])
        context = f"Материал лекции:\n{self.knowledge}\n\n" if self.knowledge else ""

        prompt = (
            f"{context}"
            f"Вопрос теста: {question}\n\n"
            f"Варианты:\n{opts}\n\n"
            f'Ответь ТОЛЬКО JSON: {{"answer": <1-{len(options)}>, "confidence": <0.0-1.0>}}'
        )

        try:
            r = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.1
            )
            raw = r.choices[0].message.content.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)
            idx = min(max(0, int(data.get("answer", 1)) - 1), len(options) - 1)
            conf = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
            return idx, conf
        except Exception as e:
            print(f"  ⚠️ Ошибка: {e}")
            return 0, 0.2

    def _solve_text(self, question: str, qtype: str) -> tuple:
        """Решает вопрос с текстовым ответом."""
        context = f"Материал лекции:\n{self.knowledge}\n\n" if self.knowledge else ""

        if qtype == "shortanswer":
            # Короткий ответ — одно слово или число
            prompt = (
                f"{context}"
                f"Вопрос: {question}\n\n"
                f"Дай КРАТКИЙ ответ (1-3 слова, число или формулу).\n"
                f"Ответь ТОЛЬКО JSON: {{\"answer\": \"<краткий ответ>\", \"confidence\": <0.0-1.0>}}"
            )
            max_tokens = 100
        else:
            # Эссе — развёрнутый ответ
            prompt = (
                f"{context}"
                f"Вопрос: {question}\n\n"
                f"Дай развёрнутый академический ответ (200-400 слов).\n"
                f"Ответь JSON: {{\"answer\": \"<текст ответа>\", \"confidence\": <0.0-1.0>}}"
            )
            max_tokens = 1500

        try:
            r = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.3
            )
            raw = r.choices[0].message.content.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()

            # Вытаскиваем JSON (может быть с лишним текстом)
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                raw = json_match.group(0)

            data = json.loads(raw)
            answer = str(data.get("answer", "")).strip()
            conf = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
            return answer, conf
        except Exception as e:
            print(f"  ⚠️ Ошибка: {e}")
            return "", 0.1

    def solve_all(self, questions: list) -> tuple:
        answers, confidences = [], []
        for i, q in enumerate(questions):
            print(f"  Вопрос {i+1}/{len(questions)} [{q.get('type')}]: {q.get('question', '')[:50]}...")
            ans, conf = self.solve_question(q)
            answers.append(ans)
            confidences.append(conf)
            shown = str(ans)[:60] if ans else "—"
            print(f"  → {shown} ({int(conf*100)}%)")
        return answers, confidences

    def make_summary(self) -> str:
        if not self.knowledge:
            return "Конспект пуст."
        try:
            r = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user",
                           "content": f"Конспект:\n{self.knowledge}\n\nРезюме в 5 пунктах:"}],
                max_tokens=500
            )
            return r.choices[0].message.content
        except Exception as e:
            return f"Ошибка: {e}"
