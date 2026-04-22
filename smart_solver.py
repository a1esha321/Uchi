"""
smart_solver.py — решает тесты на основе знаний из лекции.
Использует Groq API с ленивой инициализацией клиента.
"""

import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()


class SmartSolver:
    def __init__(self, lecture_knowledge: str = ""):
        self.knowledge = lecture_knowledge[:20000] if lecture_knowledge else ""
        self._client = None

    @property
    def client(self):
        """Ленивая инициализация — клиент создаётся только при первом вызове."""
        if self._client is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY не найден в переменных окружения")
            self._client = Groq(api_key=api_key)
        return self._client

    def solve_question(self, question: str, options: list) -> tuple:
        """Решает один вопрос. Возвращает (индекс, уверенность)."""
        if not options:
            return 0, 0.0

        opts = "\n".join([f"{i+1}. {o}" for i, o in enumerate(options)])
        context = f"Конспект лекции:\n{self.knowledge}\n\n" if self.knowledge else ""

        prompt = (
            f"{context}"
            f"Вопрос теста: {question}\n\n"
            f"Варианты:\n{opts}\n\n"
            f'Ответь ТОЛЬКО JSON: {{"answer": <номер 1-{len(options)}>, "confidence": <0.0-1.0>}}'
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
            print(f"  ⚠️ Ошибка решения: {e}")
            return 0, 0.2

    def solve_all(self, questions: list) -> tuple:
        """Решает все вопросы. Возвращает (ответы, уверенности)."""
        answers, confidences = [], []
        for i, q in enumerate(questions):
            q_text = q.get("question", "")
            options = q.get("options", [])
            print(f"  Вопрос {i+1}/{len(questions)}: {q_text[:60]}...")
            idx, conf = self.solve_question(q_text, options)
            answers.append(idx)
            confidences.append(conf)
            if options:
                print(f"  → {options[idx][:60]} ({int(conf*100)}%)")
        return answers, confidences

    def make_summary(self) -> str:
        """Краткое резюме лекции."""
        if not self.knowledge:
            return "Конспект пуст."
        try:
            r = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "user",
                    "content": f"Конспект:\n{self.knowledge}\n\nРезюме в 5 пунктах на русском:"
                }],
                max_tokens=500
            )
            return r.choices[0].message.content
        except Exception as e:
            return f"Ошибка: {e}"
