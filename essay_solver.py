"""
essay_solver.py — пишет текстовые ответы на задания.
Использует Groq API (бесплатно).
"""

import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


class EssaySolver:
    def __init__(self, lecture_knowledge: str = ""):
        self.knowledge = lecture_knowledge[:20000] if lecture_knowledge else ""

    def write_essay(self, task_text: str) -> str:
        """Читает задание и пишет ответ."""
        context = f"Конспект лекции:\n{self.knowledge}\n\n" if self.knowledge else ""
        prompt = (
            f"{context}"
            f"Задание от преподавателя:\n{task_text}\n\n"
            f"Напиши развёрнутый ответ как студент. "
            f"Пиши на русском языке, без markdown разметки, "
            f"структурировано: введение, основная часть, вывод. "
            f"Объём 200-400 слов."
        )
        try:
            r = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.7
            )
            result = r.choices[0].message.content.strip()
            print(f"Ответ написан ({len(result.split())} слов)")
            return result
        except Exception as e:
            print(f"Ошибка написания ответа: {e}")
            return ""
