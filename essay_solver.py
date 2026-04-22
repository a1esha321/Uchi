"""
essay_solver.py — пишет текстовые ответы на задания.
"""

import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()


class EssaySolver:
    def __init__(self, lecture_knowledge: str = ""):
        self.knowledge = lecture_knowledge
        self._client = None

    @property
    def client(self):
        if self._client is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY не задан")
            self._client = Groq(api_key=api_key)
        return self._client

    def write_essay(self, task_text: str) -> str:
        if not task_text or not task_text.strip():
            return ""

        context = ""
        if self.knowledge and self.knowledge.strip():
            context = f"Материал курса:\n{self.knowledge[:30000]}\n\n"

        prompt = (
            f"{context}"
            f"Ты студент заочного отделения. Выполни задание преподавателя.\n\n"
            f"Задание:\n{task_text}\n\n"
            f"Правила:\n"
            f"- Пиши живым академическим русским языком\n"
            f"- Без markdown — только чистый текст\n"
            f"- Структура: введение, основная часть, вывод\n"
            f"- Объём по требованиям, или 300-500 слов если не указан\n"
            f"- Опирайся на материал курса"
        )

        try:
            r = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.7
            )
            return r.choices[0].message.content.strip()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return ""
