"""
presence.py — вспомогательный модуль для "посещения" эфира.

ВАЖНО: Playwright sync API нельзя использовать в отдельных threading.Thread
параллельно с другим sync_playwright. Поэтому PresenceKeeper работает как
контекстный менеджер в том же потоке что и LectureListener — просто 
открывает страницу эфира один раз при старте лекции.
"""

import time
from playwright.sync_api import sync_playwright


class PresenceKeeper:
    """
    Открывает страницу эфира чтобы платформа засчитала присутствие.
    Использовать как context manager:
    
        with PresenceKeeper(url) as keeper:
            # страница открыта
            keeper.ping()  # имитация активности
    """

    def __init__(self, webinar_url: str):
        self.url = webinar_url
        self._playwright = None
        self._browser = None
        self._page = None

    def __enter__(self):
        if not self.url:
            print("⚠️ URL эфира не задан — пропускаю presence")
            return self

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            self._page = self._browser.new_page()
            self._page.goto(self.url, timeout=60000)
            print(f"👁️  Страница эфира открыта: {self.url[:50]}...")
        except Exception as e:
            print(f"⚠️ Не смог открыть эфир: {e}")
            self._cleanup()

        return self

    def ping(self):
        """Имитирует активность пользователя — движение мышью."""
        if not self._page:
            return
        try:
            self._page.mouse.move(300, 300)
            time.sleep(0.3)
            self._page.mouse.move(400, 250)
        except Exception as e:
            print(f"⚠️ Ошибка ping: {e}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cleanup()

    def _cleanup(self):
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
