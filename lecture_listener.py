"""
lecture_listener.py — слушает прямой эфир МТС Линк через API.
Каждые 5 минут забирает новые субтитры и накапливает конспект.
"""

import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.webinar.ru/v3"


class LectureListener:
    def __init__(self, event_id: str):
        self.event_id = event_id
        self.knowledge_chunks = []
        token = os.getenv("MTS_TOKEN", "")
        self.headers = {"x-auth-token": token} if token else {}

    def _get_captions(self) -> list:
        """Забираем субтитры через API МТС Линк."""
        if not self.headers:
            return []
        url = f"{BASE_URL}/events/{self.event_id}/captions"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json() or []
        except Exception as e:
            print(f"⚠️ API субтитров недоступен: {e}")
            return []

    def _captions_to_text(self, captions: list) -> str:
        return " ".join([c.get("text", "") for c in captions if c.get("text")])

    def listen_realtime(self, duration_minutes: int = 90) -> str:
        """Слушаем эфир и накапливаем конспект."""
        print(f"🎓 Слушаю лекцию (эфир {self.event_id}, {duration_minutes} мин)")

        end_time = time.time() + duration_minutes * 60
        last_text = ""
        check_interval = 300  # 5 минут

        while time.time() < end_time:
            remaining = int((end_time - time.time()) / 60)
            print(f"📡 Проверяю субтитры... (осталось ~{remaining} мин)")

            captions = self._get_captions()
            full_text = self._captions_to_text(captions)

            if full_text and full_text != last_text:
                new_part = full_text[len(last_text):].strip()
                if new_part:
                    self.knowledge_chunks.append(new_part)
                    last_text = full_text
                    print(f"📝 Записал {len(new_part.split())} слов")

            sleep_time = min(check_interval, end_time - time.time())
            if sleep_time > 0:
                time.sleep(sleep_time)

        print(f"✅ Лекция завершена, конспект: {len(self.get_full_knowledge().split())} слов")
        return self.get_full_knowledge()

    def get_full_knowledge(self) -> str:
        return "\n\n".join(self.knowledge_chunks)
