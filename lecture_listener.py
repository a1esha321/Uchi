"""
lecture_listener.py — слушает прямой эфир МТС Линк и накапливает знания.

Каждые 5 минут забирает новые субтитры через API МТС Линк
и сохраняет их как конспект лекции.
"""

import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

MTS_TOKEN = os.getenv("MTS_TOKEN")
BASE_URL = "https://api.webinar.ru/v3"


class LectureListener:
    def __init__(self, event_id: str):
        """
        event_id — ID эфира в МТС Линк.
        Найти можно в URL эфира: events.mts-link.ru/XXXXXX
        """
        self.event_id = event_id
        self.knowledge_chunks = []
        self.headers = {"x-auth-token": MTS_TOKEN}

    def _get_captions(self) -> list:
        """Забираем субтитры через API МТС Линк"""
        url = f"{BASE_URL}/events/{self.event_id}/captions"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json() or []
        except Exception as e:
            print(f"⚠️ Ошибка API субтитров: {e}")
            return []

    def _captions_to_text(self, captions: list) -> str:
        """Собираем весь текст субтитров в одну строку"""
        return " ".join([c.get("text", "") for c in captions if c.get("text")])

    def listen_realtime(self, duration_minutes: int = 90) -> str:
        """
        Основной метод — слушаем эфир в течение duration_minutes минут.
        Каждые 5 минут проверяем новые субтитры и добавляем в конспект.

        Возвращает полный конспект лекции.
        """
        print(f"🎓 Слушаю лекцию (эфир ID: {self.event_id})")
        print(f"⏱️  Длительность: {duration_minutes} минут")
        print("-" * 40)

        end_time = time.time() + duration_minutes * 60
        last_text = ""
        check_interval = 300  # 5 минут

        while time.time() < end_time:
            remaining = int((end_time - time.time()) / 60)
            print(f"📡 Проверяю субтитры... (осталось ~{remaining} мин)")

            captions = self._get_captions()
            full_text = self._captions_to_text(captions)

            # Берём только новый текст (то что появилось с прошлой проверки)
            if full_text and full_text != last_text:
                new_part = full_text[len(last_text):].strip()
                if new_part:
                    self.knowledge_chunks.append(new_part)
                    last_text = full_text
                    words = len(new_part.split())
                    print(f"📝 Записал {words} новых слов из лекции")
            else:
                print("⏸️  Новых субтитров пока нет")

            # Ждём следующей проверки
            sleep_time = min(check_interval, end_time - time.time())
            if sleep_time > 0:
                time.sleep(sleep_time)

        print("-" * 40)
        print(f"✅ Лекция завершена!")
        total_words = len(self.get_full_knowledge().split())
        print(f"📚 Итого в конспекте: {total_words} слов")

        return self.get_full_knowledge()

    def get_full_knowledge(self) -> str:
        """Возвращает полный конспект лекции"""
        return "\n\n".join(self.knowledge_chunks)

    def save_notes(self, filename: str = None):
        """Сохраняет конспект в текстовый файл"""
        if not filename:
            filename = f"notes_{self.event_id}.txt"

        with open(filename, "w", encoding="utf-8") as f:
            f.write(self.get_full_knowledge())

        print(f"💾 Конспект сохранён: {filename}")
        return filename
