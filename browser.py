"""
browser.py — управление браузером через Playwright.
Настроен для headless режима на Railway.

ВАЖНО: замени селекторы под свой сайт университета!
Открой сайт в Chrome → F12 → найди нужные элементы → скопируй селекторы.
"""

from playwright.sync_api import sync_playwright
import os
import time
from dotenv import load_dotenv

load_dotenv()


class UniBrowser:
    def __init__(self, headless: bool = True):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        self.page = self.browser.new_page()

    def login(self):
        """Логин на сайт университета. Замени селекторы под свой сайт."""
        self.page.goto(os.getenv("UNI_URL", ""))
        self.page.wait_for_load_state("networkidle")
        # ЗАМЕНИ НА СВОИ СЕЛЕКТОРЫ
        self.page.fill('input[name="username"]', os.getenv("UNI_LOGIN", ""))
        self.page.fill('input[name="password"]', os.getenv("UNI_PASSWORD", ""))
        self.page.click('button[type="submit"]')
        self.page.wait_for_load_state("networkidle")
        print("Залогинились")

    def goto(self, url: str):
        self.page.goto(url)
        self.page.wait_for_load_state("networkidle")
        time.sleep(2)

    def get_quiz_data(self) -> list:
        """Собирает вопросы теста. Замени селекторы под свой сайт."""
        questions = []
        # ЗАМЕНИ НА СВОИ СЕЛЕКТОРЫ
        blocks = self.page.query_selector_all(".que")
        for block in blocks:
            q_el = block.query_selector(".qtext")
            if not q_el:
                continue
            question_text = q_el.inner_text().strip()
            radios = block.query_selector_all('.answer input[type="radio"]')
            if radios:
                labels = block.query_selector_all('.answer label')
                options = [l.inner_text().strip() for l in labels]
                questions.append({
                    "question": question_text,
                    "options": options,
                    "elements": list(radios)
                })
        print(f"Найдено вопросов: {len(questions)}")
        return questions

    def start_quiz(self) -> bool:
        btn = (
            self.page.query_selector('button:has-text("Начать")') or
            self.page.query_selector('a:has-text("Начать тестирование")')
        )
        if btn:
            btn.click()
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)
            return True
        return False

    def click_answer(self, element):
        element.click()
        time.sleep(0.3)

    def submit_quiz(self):
        """Отправляет тест. Пауза для проверки уже реализована через Telegram."""
        finish = (
            self.page.query_selector('input[value="Закончить попытку"]') or
            self.page.query_selector('button:has-text("Закончить попытку")')
        )
        if finish:
            finish.click()
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)

        submit = (
            self.page.query_selector('input[value="Отправить всё и завершить тест"]') or
            self.page.query_selector('button:has-text("Отправить всё и завершить тест")')
        )
        if submit:
            submit.click()
            time.sleep(2)

        confirm = self.page.query_selector('.modal-footer button.btn-primary')
        if confirm:
            confirm.click()
            self.page.wait_for_load_state("networkidle")
        print("Тест завершён")

    def get_task_text(self) -> str:
        task_el = (
            self.page.query_selector(".box.generalbox") or
            self.page.query_selector("#intro") or
            self.page.query_selector('[role="main"]')
        )
        return task_el.inner_text().strip() if task_el else ""

    def fill_text_answer(self, text: str):
        iframe = self.page.query_selector('iframe[id*="editor"]')
        if iframe:
            frame = iframe.content_frame()
            body = frame.query_selector("body")
            if body:
                body.fill(text)
                return
        textarea = self.page.query_selector("textarea")
        if textarea:
            textarea.fill(text)

    def submit_assignment(self):
        btn = (
            self.page.query_selector('input[value="Сохранить изменения"]') or
            self.page.query_selector('button:has-text("Сохранить")')
        )
        if btn:
            btn.click()
            self.page.wait_for_load_state("networkidle")
        print("Задание отправлено")

    def close(self):
        self.browser.close()
        self.playwright.stop()
