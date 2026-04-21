"""
essay_solver.py — пишет эссе используя Groq API (бесплатно).
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"


class EssaySolver:
    def __init__(self, lecture_knowledge: str = ""):
        self.knowledge = lecture_knowledge[:20000] if lecture_knowledge else ""

    def write_essay(self, task_text: str) -> str:
        system = """Ты студент заочного отделения. Пиши ответы как студент — академическим языком.
Без markdown разметки, только чистый текст. На русском языке."""
        if self.knowledge:
            system += f"\n\nМатериал лекции:\n{self.knowledge}"

        response = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Выполни задание:\n\n{task_text}"}
                ],
                "max_tokens": 1000
            },
            timeout=60
        )
        return response.json()["choices"][0]["message"]["content"].strip()
