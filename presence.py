"""
presence.py — держит страницу эфира МТС Линк открытой,
чтобы платформа засчитала присутствие студента.

Запускается в отдельном потоке параллельно с lecture_listener.
"""

import threading
import time
import os
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()


class PresenceKeeper:
    def __init__(self, webinar_url: str):
        """
        webinar_url — прямая ссылка на эфир.
        Например: https://events.mts-link.ru/12345678
        """
        self.url = webinar_url
        self.running = False
        self._thread = None

    def start(self):
        """Запускаем в фоновом потоке"""
        self.running = True
        self._thread = threading.Thread(target=self._keep_alive, daemon=True)
        self._thread.start()
        print(f"👁️  Присутствие на эфире активировано: {self.url}")

    def stop(self):
        """Останавливаем"""
        self.running = False
        print("🛑 Присутствие завершено")

    def _keep_alive(self):
        """
        Основной цикл: открываем страницу эфира и каждые 2 минуты
        имитируем активность (движение мышью), чтобы платформа
        не засчитала нас как "отключившегося".
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            try:
                # Заходим на страницу эфира
                page.goto(self.url, timeout=30000)
                page.wait_for_load_state("networkidle")
                print("✅ Страница эфира открыта")

                activity_count = 0

                while self.running:
                    try:
                        # Имитируем движение мыши — платформа видит активного пользователя
                        page.mouse.move(300, 300)
                        time.sleep(0.5)
                        page.mouse.move(400, 250)

                        activity_count += 1
                        print(f"✅ Активность #{activity_count} подтверждена")

                        # Ждём 2 минуты до следующей активности
                        time.sleep(120)

                    except Exception as e:
                        print(f"⚠️ Ошибка активности: {e}")
                        time.sleep(30)

            except Exception as e:
                print(f"❌ Не удалось открыть страницу эфира: {e}")
            finally:
                browser.close()
