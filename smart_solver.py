"""
smart_solver.py — решает тесты на основе знаний из лекции.
Использует Groq API (бесплатно).
"""

import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
print(f"GROQ_API_KEY present: {bool(api_key)}")

client = Groq(api_key=api_key)


class SmartSolver:
    def __init__(self, lecture_knowledge: str = ""):
        self.knowledge = lecture_knowledge[:20000] if lecture_knowledge else ""

    def solve_question(self, question: str, options: list) -> tuple:
        """Решает один вопрос. Возвращает (индекс, уверенность)."""
        opts = "\n".join([f"{i+1}. {o}" for i, o in enumerate(options)])
        context = f"Конспект лекции:\n{self.knowledge}\n\n" if self.knowledge else ""

        prompt = (
            f"{context}"
            f"Вопрос теста: {question}\n\n"
            f"Варианты:\n{opts}\n\n"
            f'Ответь ТОЛЬКО JSON без пояснений: {{"answer": <номер 1-{len(options)}>, "confidence": <0.0-1.0>}}'
        )

        try:
            r = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.1
            )
            raw = r.choices[0].message.content.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)
            idx = max(0, int(data.get("answer", 1)) - 1)
            conf = float(data.get("confidence", 0.5))
            idx = min(idx, len(options) - 1)
            conf = max(0.0, min(1.0, conf))
            return idx, conf
        except Exception as e:
            print(f"  Ошибка парсинга ответа: {e}")
            return 0, 0.2

    def solve_all(self, questions: list) -> tuple:
        """Решает все вопросы. Возвращает (ответы, уверенности)."""
        answers, confidences = [], []
        for i, q in enumerate(questions):
            print(f"  Вопрос {i+1}/{len(questions)}: {q['question'][:60]}...")
            idx, conf = self.solve_question(q["question"], q["options"])
            answers.append(idx)
            confidences.append(conf)
            answer_text = q["options"][idx] if q["options"] else "—"
            print(f"  -> {answer_text} ({int(conf*100)}%)")
        return answers, confidences

    def make_summary(self) -> str:
        """Краткое резюме лекции."""
        if not self.knowledge:
            return "Конспект пуст."
        try:
            r = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "user",
                    "content": f"Вот конспект лекции:\n{self.knowledge}\n\nСоставь краткое резюме в 5 пунктах на русском языке."
                }],
                max_tokens=500
            )
            return r.choices[0].message.content
        except Exception as e:
            return f"Ошибка генерации резюме: {e}"
