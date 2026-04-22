"""
lecture_listener.py — слушает эфир МТС Линк и накапливает конспект.
"""

import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

MTS_TOKEN = os.getenv("MTS_TOKEN", "")
BASE_URL = "https://api.webinar.ru/v3"


class LectureListener:
    def __init__(self, event_id: str):
        self.event_id = event_id
        self.knowledge_chunks = []
        self.headers = {"x-auth-token": MTS_TOKEN}

    def _get_captions(self) -> list:
        if not MTS_TOKEN:
            return []
        try:
            r = requests.get(
                f"{BASE_URL}/events/{self.event_id}/captions",
                headers=self.headers, timeout=10
            )
            return r.json() or []
        except Exception as e:
            print(f"Ошибка субтитров: {e}")
            return []

    def _captions_to_text(self, captions: list) -> str:
        return " ".join([c.get("text", "") for c in captions if c.get("text")])

    def listen_realtime(self, duration_minutes: int = 90) -> str:
        print(f"Слушаю лекцию (эфир {self.event_id}, {duration_minutes} мин)")
        end_time = time.time() + duration_minutes * 60
        last_text = ""

        while time.time() < end_time:
            remaining = int((end_time - time.time()) / 60)
            print(f"Проверяю субтитры... (осталось ~{remaining} мин)")

            captions = self._get_captions()
            full_text = self._captions_to_text(captions)

            if full_text and full_text != last_text:
                new_part = full_text[len(last_text):].strip()
                if new_part:
                    self.knowledge_chunks.append(new_part)
                    last_text = full_text
                    print(f"Записал {len(new_part.split())} слов")

            sleep_time = min(300, end_time - time.time())
            if sleep_time > 0:
                time.sleep(sleep_time)

        print(f"Лекция завершена. Слов в конспекте: {len(self.get_full_knowledge().split())}")
        return self.get_full_knowledge()

    def get_full_knowledge(self) -> str:
        return "\n\n".join(self.knowledge_chunks)

    def save_notes(self, filename: str = None) -> str:
        os.makedirs("notes", exist_ok=True)
        if not filename:
            filename = f"notes/{self.event_id}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(self.get_full_knowledge())
        print(f"Конспект сохранён: {filename}")
        return filename
