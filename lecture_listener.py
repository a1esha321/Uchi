"""
lecture_listener.py — слушает эфир МТС Линк через API.
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
        if not self.headers:
            return []
        try:
            r = requests.get(
                f"{BASE_URL}/events/{self.event_id}/captions",
                headers=self.headers,
                timeout=10
            )
            r.raise_for_status()
            return r.json() or []
        except Exception as e:
            print(f"⚠️ API субтитров: {e}")
            return []

    def _text(self, captions: list) -> str:
        return " ".join([c.get("text", "") for c in captions if c.get("text")])

    def listen_realtime(self, duration_minutes: int = 90) -> str:
        print(f"🎓 Слушаю лекцию ({duration_minutes} мин)")
        end_time = time.time() + duration_minutes * 60
        last_text = ""

        while time.time() < end_time:
            captions = self._get_captions()
            full_text = self._text(captions)

            if full_text and full_text != last_text:
                new_part = full_text[len(last_text):].strip()
                if new_part:
                    self.knowledge_chunks.append(new_part)
                    last_text = full_text
                    print(f"📝 +{len(new_part.split())} слов")

            sleep_time = min(300, end_time - time.time())
            if sleep_time > 0:
                time.sleep(sleep_time)

        return self.get_full_knowledge()

    def get_full_knowledge(self) -> str:
        return "\n\n".join(self.knowledge_chunks)
