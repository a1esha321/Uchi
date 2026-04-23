"""
quiz_digest.py — генерирует учебную выжимку из сданного теста.

После каждого теста бот создаёт карточку:
  - о чём был тест
  - что важно запомнить
  - где была низкая уверенность (риски)

Дайджест сохраняется в digests/ и добавляется в конспекты предмета —
то есть следующий тест получит его как контекст.
"""

import os
import re
from datetime import datetime
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

DIGESTS_DIR = "digests"


class QuizDigest:
    def __init__(self, subject_name: str):
        self.subject_name = subject_name
        self._client = None

    @property
    def client(self):
        if self._client is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY не задан")
            self._client = Groq(api_key=api_key)
        return self._client

    def generate(self, questions: list, answers: list, confidences: list, grade: str = "") -> str:
        """
        Генерирует дайджест теста.
        Возвращает строку в Telegram HTML или "" если не удалось.
        """
        if not questions:
            return ""

        qa_lines = []
        risky_lines = []

        for i, (q, ans, conf) in enumerate(zip(questions, answers, confidences)):
            qtext = q.get("question", "")[:200]
            options = q.get("options", [])

            if isinstance(ans, int) and options:
                ans_text = options[ans] if 0 <= ans < len(options) else str(ans)
            else:
                ans_text = str(ans)[:150]

            qa_lines.append(f"В{i+1}: {qtext}\nОтвет: {ans_text}")

            if conf < 0.6:
                risky_lines.append(f"- {qtext[:100]} → {ans_text[:60]}")

        qa_text = "\n\n".join(qa_lines)
        risky_block = "\n".join(risky_lines[:5]) if risky_lines else "нет"
        grade_line = f"Итоговая оценка: {grade}\n" if grade else ""

        prompt = (
            f"Предмет: {self.subject_name}\n"
            f"{grade_line}"
            f"Студент только что сдал тест. Вопросы и выбранные ответы:\n\n"
            f"{qa_text[:6000]}\n\n"
            f"Напиши учебный дайджест на русском языке. Строго по структуре:\n\n"
            f"ТЕМА: одна строка — суть теста в двух словах\n\n"
            f"КЛЮЧЕВЫЕ ФАКТЫ:\n"
            f"• (3–5 конкретных утверждений из правильных ответов)\n\n"
            f"ЗАПОМНИ:\n"
            f"(1–2 формулировки, которые точно встретятся снова)\n\n"
            f"СЛАБЫЕ МЕСТА:\n"
            f"{risky_block}\n\n"
            f"Пиши коротко и по делу. Не пересказывай вопросы дословно. "
            f"Это карточка для повторения перед сессией."
        )

        try:
            r = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=700,
                temperature=0.4,
            )
            raw = r.choices[0].message.content.strip()
            return self._format_html(raw, grade)
        except Exception as e:
            print(f"  ⚠️ QuizDigest: {e}")
            return ""

    def _format_html(self, text: str, grade: str) -> str:
        """Превращает plain text в Telegram HTML."""
        header = f"📋 <b>Дайджест теста: {self.subject_name}</b>"
        if grade:
            header += f"  |  оценка: <b>{grade}</b>"

        lines = [header, ""]

        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                lines.append("")
                continue

            # Секции — жирным (ТЕМА:, КЛЮЧЕВЫЕ ФАКТЫ:, ЗАПОМНИ:, СЛАБЫЕ МЕСТА:)
            if re.match(r"^(ТЕМА|КЛЮЧЕВЫЕ ФАКТЫ|ЗАПОМНИ|СЛАБЫЕ МЕСТА)[:\s]", stripped, re.I):
                lines.append(f"\n<b>{stripped}</b>")
            elif stripped.startswith(("•", "-", "*")):
                lines.append(f"  {stripped}")
            else:
                lines.append(stripped)

        return "\n".join(lines).strip()

    def save(self, subject_id: str, html_text: str) -> str:
        """
        Сохраняет дайджест как plain-text файл.
        Возвращает путь — его можно добавить в notes_files предмета,
        тогда следующий тест получит этот дайджест как контекст для AI.
        """
        os.makedirs(DIGESTS_DIR, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d_%H%M")
        path = f"{DIGESTS_DIR}/{subject_id}_{date_str}.txt"

        plain = re.sub(r"<[^>]+>", "", html_text)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"Дайджест теста: {self.subject_name}\n")
            f.write(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
            f.write("=" * 50 + "\n\n")
            f.write(plain)

        return path
