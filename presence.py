"""
presence.py — держит страницу эфира открытой для фиксации присутствия.
На Railway запускается в headless режиме.
"""

import threading
import time
import os
from dotenv import load_dotenv

load_dotenv()


class PresenceKeeper:
    def __init__(self, webinar_url: str):
        self.url = webinar_url
        self.running = False
        self._thread = None

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._keep_alive, daemon=True)
        self._thread.start()
        print(f"Присутствие активировано: {self.url}")

    def stop(self):
        self.running = False
        print("Присутствие завершено")

    def _keep_alive(self):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                page = browser.new_page()
                page.goto(self.url, timeout=30000)
                page.wait_for_load_state("networkidle")
                print("Страница эфира открыта")

                count = 0
                while self.running:
                    page.mouse.move(300 + count, 300)
                    count = (count + 10) % 100
                    print(f"Активность #{count} подтверждена")
                    time.sleep(120)

                browser.close()
        except Exception as e:
            print(f"Ошибка присутствия: {e}")
