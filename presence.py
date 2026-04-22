"""
presence.py — открывает страницу эфира для учёта присутствия.
"""

import time
from playwright.sync_api import sync_playwright


class PresenceKeeper:
    def __init__(self, webinar_url: str):
        self.url = webinar_url
        self._playwright = None
        self._browser = None
        self._page = None

    def __enter__(self):
        if not self.url:
            return self
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            self._page = self._browser.new_page()
            self._page.goto(self.url, timeout=60000)
            print(f"👁️  Страница эфира открыта")
        except Exception as e:
            print(f"⚠️ Эфир недоступен: {e}")
            self._cleanup()
        return self

    def ping(self):
        if not self._page:
            return
        try:
            self._page.mouse.move(300, 300)
            time.sleep(0.3)
            self._page.mouse.move(400, 250)
        except Exception:
            pass

    def __exit__(self, *args):
        self._cleanup()

    def _cleanup(self):
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
