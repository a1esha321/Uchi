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
                raise ValueError("GROQ_API_KEY не найден!")
            self._client = Groq(api_key=api_key)
        return self._client

    def write_essay(self, task_text: str) -> str:
        print(f"✍️  Читаю задание: {task_text[:100]}...")
        context = f"Конспект лекции:\n{self.knowledge[:30000]}\n\n" if self.knowledge.strip() else ""
        prompt = (
            f"{context}"
            f"Ты студент заочного отделения. Выполни задание преподавателя.\n"
            f"Пиши живым академическим языком, без markdown, только чистый текст.\n\n"
            f"Задание: {task_text}"
        )
        try:
            r = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000
            )
            result = r.choices[0].message.content.strip()
            print(f"✅ Ответ написан ({len(result.split())} слов)")
            return result
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return ""
