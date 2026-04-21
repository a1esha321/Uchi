"""
smart_solver.py — Claude решает тесты на основе знаний из лекции.
Возвращает ответ И уверенность (0.0 — 1.0) для каждого вопроса.
"""

import anthropic
import os
import json
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


class SmartSolver:
    def __init__(self, lecture_knowledge: str = ""):
        trimmed = lecture_knowledge[:50000]

        knowledge_block = f"""Вот конспект лекций по предмету:
=== КОНСПЕКТ ===
{trimmed}
=== КОНЕЦ ===
""" if trimmed.strip() else "Используй общие академические знания."

        self.system_prompt = f"""Ты студент, отвечаешь на вопросы теста.

{knowledge_block}

Отвечай СТРОГО в формате JSON:
{{"answer": <номер от 1 до N>, "confidence": <число от 0.0 до 1.0>, "reason": "<одно предложение почему>"}}

Правила:
- answer: номер правильного варианта (1, 2, 3...)
- confidence: 1.0 = абсолютно уверен, 0.5 = не уверен, 0.2 = угадываю
- reason: краткое объяснение выбора
- Никакого текста кроме JSON"""

    def solve_question(self, question: str, options: list) -> tuple:
        """
        Решает один вопрос.
        Возвращает (индекс_ответа, уверенность, причина).
        """
        options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])

        try:
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=150,
                system=self.system_prompt,
                messages=[{
                    "role": "user",
                    "content": f"Вопрос: {question}\n\nВарианты:\n{options_text}"
                }]
            )

            raw = message.content[0].text.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)

            answer_num = int(data.get("answer", 1))
            confidence = float(data.get("confidence", 0.5))
            reason = data.get("reason", "")

            idx = max(0, min(answer_num - 1, len(options) - 1))
            confidence = max(0.0, min(1.0, confidence))

            return idx, confidence, reason

        except Exception as e:
            print(f"  Ошибка парсинга: {e}")
            return 0, 0.2, "Ошибка парсинга — выбран первый вариант"

    def solve_all(self, questions: list) -> tuple:
        """
        Решает все вопросы теста.
        Возвращает (ответы, уверенности, причины).
        """
        answers, confidences, reasons = [], [], []

        for i, q in enumerate(questions):
            print(f"  Вопрос {i+1}/{len(questions)}: {q['question'][:60]}...")
            idx, conf, reason = self.solve_question(q["question"], q["options"])
            answers.append(idx)
            confidences.append(conf)
            reasons.append(reason)

            answer_text = q["options"][idx] if q["options"] else "—"
            print(f"     -> {answer_text} ({int(conf*100)}%)")

        return answers, confidences, reasons

    def make_summary(self) -> str:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=self.system_prompt,
            messages=[{"role": "user", "content": "Составь краткое резюме лекции в 5-7 пунктах."}]
        )
        return message.content[0].text
