"""
essay_solver.py — пишет текстовые ответы на задания.
Читает требования преподавателя и отвечает на основе конспектов.
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
                raise ValueError("GROQ_API_KEY не найден в переменных окружения")
            self._client = Groq(api_key=api_key)
        return self._client

    def write_essay(self, task_text: str) -> str:
        """Читает требования преподавателя и пишет ответ."""
        if not task_text or not task_text.strip():
            return ""

        print(f"✍️  Читаю задание: {task_text[:100]}...")

        context = ""
        if self.knowledge and self.knowledge.strip():
            context = f"Конспект лекций по предмету:\n{self.knowledge[:30000]}\n\n"

        prompt = (
            f"{context}"
            f"Ты студент заочного отделения. Прочитай требования преподавателя "
            f"и выполни задание.\n\n"
            f"Требования:\n{task_text}\n\n"
            f"Правила:\n"
            f"- Пиши живым академическим языком, как студент\n"
            f"- Без markdown-разметки — только чистый текст\n"
            f"- Структурируй: введение, основная часть, вывод\n"
            f"- Если объём не указан — 200-400 слов\n"
            f"- Опирайся на конспект лекций где это уместно\n"
            f"- Пиши на русском языке"
        )

        try:
            r = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.7
            )
            result = r.choices[0].message.content.strip()
            print(f"✅ Ответ готов ({len(result.split())} слов)")
            return result
        except Exception as e:
            print(f"❌ Ошибка генерации: {e}")
            return ""
