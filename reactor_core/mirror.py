import os
import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Tuple

from groq import Groq

logger = logging.getLogger(__name__)

GROQ_MODEL = "llama-3.3-70b-versatile"


class KnowledgeMirror:
    """Зеркало знаний — трекинг реального уровня освоения тем."""

    def __init__(self, db_path: str = "knowledge.db"):
        if not os.getenv("GROQ_API_KEY"):
            raise RuntimeError("GROQ_API_KEY не задан в .env")

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.groq = Groq()
        self._init_db()
        logger.info("KnowledgeMirror инициализирован")

    def _init_db(self):
        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS user_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id TEXT,
                topic TEXT,
                confidence REAL DEFAULT 0.5,
                last_quizzed TIMESTAMP,
                times_correct INTEGER DEFAULT 0,
                times_incorrect INTEGER DEFAULT 0,
                UNIQUE(subject_id, topic)
            );
            CREATE TABLE IF NOT EXISTS learning_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id TEXT,
                topic TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                was_correct INTEGER,
                notes TEXT
            );
        """)
        self.conn.commit()

    def update_confidence(self, subject_id: str, topic: str, is_correct: bool):
        """
        Обновляем счётчики и пересчитываем confidence двумя запросами,
        чтобы не было гонки в SQL-выражении.
        """
        now = datetime.now().isoformat()

        # 1. UPSERT счётчиков
        self.cursor.execute("""
            INSERT INTO user_knowledge
                (subject_id, topic, last_quizzed, times_correct, times_incorrect)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(subject_id, topic) DO UPDATE SET
                last_quizzed = excluded.last_quizzed,
                times_correct = times_correct + ?,
                times_incorrect = times_incorrect + ?
        """, (
            subject_id, topic, now,
            1 if is_correct else 0,
            0 if is_correct else 1,
            1 if is_correct else 0,
            0 if is_correct else 1,
        ))

        # 2. Пересчёт confidence по формуле Лапласа: (correct + 1) / (total + 2)
        self.cursor.execute("""
            UPDATE user_knowledge
            SET confidence = (times_correct + 1.0) / (times_correct + times_incorrect + 2.0)
            WHERE subject_id = ? AND topic = ?
        """, (subject_id, topic))

        self.conn.commit()
        logger.info(f"Уверенность '{topic}' обновлена: {'+' if is_correct else '-'}")

    def get_weak_topics(self, subject_id: Optional[str] = None,
                        threshold: float = 0.6) -> List[Tuple]:
        query = "SELECT subject_id, topic, confidence FROM user_knowledge WHERE confidence < ?"
        params: list = [threshold]
        if subject_id is not None:
            query += " AND subject_id = ?"
            params.append(subject_id)
        query += " ORDER BY confidence ASC"
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    def get_strong_topics(self, subject_id: Optional[str] = None,
                          threshold: float = 0.8) -> List[Tuple]:
        query = "SELECT subject_id, topic, confidence FROM user_knowledge WHERE confidence >= ?"
        params: list = [threshold]
        if subject_id is not None:
            query += " AND subject_id = ?"
            params.append(subject_id)
        query += " ORDER BY confidence DESC"
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    def generate_micro_quiz(self, subject_name: str, topic: str,
                            context_text: str) -> Tuple[str, str]:
        """Генерит один короткий вопрос + эталонный ответ на основе конспекта."""
        prompt = (
            f'Ты преподаватель по предмету "{subject_name}". '
            f'На основе материала ниже придумай ОДИН короткий вопрос по теме "{topic}", '
            f"на который можно ответить в 1-3 предложениях.\n\n"
            f"Формат ответа строго такой:\n"
            f"Вопрос: <текст вопроса>\n"
            f"Правильный ответ: <эталонный ответ>\n\n"
            f"Материал:\n{context_text[:3000]}"
        )

        try:
            resp = self.groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300,
            )
            text = resp.choices[0].message.content
            if "Правильный ответ:" in text:
                q_part, a_part = text.split("Правильный ответ:", 1)
                question = q_part.replace("Вопрос:", "").strip()
                answer = a_part.strip()
            else:
                question = text.strip()
                answer = "Эталонный ответ не распознан."
            return question, answer
        except Exception as e:
            logger.error(f"Ошибка генерации квиза: {e}")
            return f"Вопрос по теме '{topic}' временно недоступен.", ""

    def evaluate_user_answer(self, user_answer: str, correct_answer: str) -> bool:
        """Проверяет ответ студента семантически, не буквально."""
        prompt = (
            f"Сравни ответ студента с эталонным. Оцени по сути, не по формулировкам.\n"
            f"Ответь строго одним словом: ДА или НЕТ.\n\n"
            f"Эталон: {correct_answer}\n"
            f"Ответ студента: {user_answer}"
        )
        try:
            resp = self.groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=5,
            )
            verdict = resp.choices[0].message.content.strip().upper()
            return verdict.startswith("ДА")
        except Exception as e:
            logger.error(f"Ошибка оценки: {e}")
            return False

    def should_remind(self, days_since_last_quiz: int = 3) -> bool:
        self.cursor.execute("SELECT MAX(last_quizzed) FROM user_knowledge")
        last = self.cursor.fetchone()[0]
        if last is None:
            return True
        last_date = datetime.fromisoformat(last)
        return (datetime.now() - last_date).days >= days_since_last_quiz

    def get_knowledge_summary(self, subject_id: Optional[str] = None) -> str:
        weak = self.get_weak_topics(subject_id)
        strong = self.get_strong_topics(subject_id)

        report = "📊 <b>Сводка знаний</b>\n\n"
        if weak:
            report += "⚠️ <b>Требуют внимания:</b>\n"
            for sid, topic, conf in weak[:10]:
                report += f"  • {topic}: {conf*100:.0f}%\n"
        if strong:
            report += "\n✅ <b>Уверенные темы:</b>\n"
            for sid, topic, conf in strong[:10]:
                report += f"  • {topic}: {conf*100:.0f}%\n"
        if not weak and not strong:
            report += "Нет данных. Пройди /learn чтобы начать."
        return report

    def log_session(self, subject_id: str, topic: str,
                    start: datetime, end: datetime,
                    was_correct: bool, notes: str = ""):
        self.cursor.execute("""
            INSERT INTO learning_sessions
                (subject_id, topic, start_time, end_time, was_correct, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (subject_id, topic, start.isoformat(), end.isoformat(),
              1 if was_correct else 0, notes))
        self.conn.commit()
