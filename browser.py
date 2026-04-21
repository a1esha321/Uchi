"""
browser.py — управление браузером для campus.fa.ru (Moodle).
Настроено под реальный сайт Финансового университета.
"""

from playwright.sync_api import sync_playwright
import os, time
from dotenv import load_dotenv
load_dotenv()


class UniBrowser:
    def __init__(self, headless: bool = False):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.page = self.browser.new_page()

    # ─── АВТОРИЗАЦИЯ ──────────────────────────────────────────

    def login(self):
        self.page.goto("https://campus.fa.ru/login/index.php")
        self.page.wait_for_load_state("networkidle")
        self.page.fill('input[name="username"]', os.getenv("UNI_LOGIN"))
        self.page.fill('input[name="password"]', os.getenv("UNI_PASSWORD"))
        self.page.click('#loginbtn')
        self.page.wait_for_load_state("networkidle")
        print("✅ Залогинились на campus.fa.ru")

    def goto(self, url: str):
        self.page.goto(url)
        self.page.wait_for_load_state("networkidle")
        time.sleep(2)

    # ─── СПИСОК КУРСОВ (с пагинацией) ─────────────────────────

    def get_my_courses(self) -> list:
        """
        Собирает ВСЕ курсы студента, обходя пагинацию.
        На campus.fa.ru курсы показываются по 12 штук — нужно
        листать страницы пока не соберём все.
        """
        self.page.goto("https://campus.fa.ru/my/courses.php")
        self.page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Сначала показываем сразу все курсы — меняем "Показать 12" на "Все"
        try:
            show_all = self.page.query_selector('[data-value="0"]')  # "Все"
            if not show_all:
                # Кликаем на выпадушку "Показать 12"
                dropdown = self.page.query_selector('.paging select, [data-action="limit"]')
                if dropdown:
                    dropdown.select_option(value="0")
                    self.page.wait_for_load_state("networkidle")
                    time.sleep(2)
        except:
            pass

        courses = []
        page_num = 1

        while True:
            print(f"  📄 Страница курсов {page_num}...")
            seen_before = len(courses)
            seen_urls = {c["url"] for c in courses}

            # Собираем карточки курсов на текущей странице
            course_els = self.page.query_selector_all(
                '.coursename a, '
                '.multiline a, '
                'a[href*="/course/view.php"]'
            )

            for el in course_els:
                href = el.get_attribute("href") or ""
                name = el.inner_text().strip()
                if href and "course/view.php" in href and href not in seen_urls and name:
                    # Берём название из карточки (более читаемое)
                    try:
                        card = el.evaluate("el => el.closest('.coursecard, .coursebox, .card')")
                        card_name_el = self.page.query_selector(f'[href="{href}"]')
                        if card_name_el:
                            name = card_name_el.inner_text().strip() or name
                    except:
                        pass
                    courses.append({"name": name, "url": href})
                    seen_urls.add(href)

            # Проверяем есть ли кнопка "следующая страница"
            next_btn = self.page.query_selector(
                'a[aria-label="Далее"], '
                '.paging-next a, '
                '[data-action="next-page"]:not([disabled])'
            )

            if next_btn and len(courses) > seen_before:
                next_btn.click()
                self.page.wait_for_load_state("networkidle")
                time.sleep(2)
                page_num += 1
            else:
                break

        # Фильтруем нерелевантные курсы
        relevant = [c for c in courses if _is_academic_course(c["name"])]
        print(f"📚 Найдено курсов: {len(relevant)} (из {len(courses)} всего)")
        return relevant

    # ─── ДЕДЛАЙНЫ ИЗ КАЛЕНДАРЯ ────────────────────────────────

    def get_upcoming_deadlines(self) -> list:
        """
        Читает календарь на главной странице campus.fa.ru.
        Возвращает список дедлайнов с датами и названиями.
        Красные даты в календаре = дедлайны!
        """
        self.page.goto("https://campus.fa.ru/")
        self.page.wait_for_load_state("networkidle")
        time.sleep(2)

        deadlines = []

        # Красные дни в календаре — это дедлайны
        deadline_days = self.page.query_selector_all(
            '.calendar_event_course, '
            'td.today a, '
            'td[data-region="day"] a.hasevent'
        )

        for day in deadline_days:
            try:
                day.click()
                time.sleep(0.5)

                # Всплывающее окно с событием
                popup = self.page.query_selector('.eventlist, .popover-body, [data-region="event-list-content"]')
                if popup:
                    text = popup.inner_text().strip()
                    if text:
                        deadlines.append(text)
            except:
                pass

        # Также смотрим блок предстоящих событий
        upcoming = self.page.query_selector_all('.event a, .upcomingname')
        for el in upcoming:
            text = el.inner_text().strip()
            if text and text not in deadlines:
                deadlines.append(text)

        print(f"📅 Найдено дедлайнов: {len(deadlines)}")
        return deadlines

    # ─── АКТИВНОСТИ КУРСА ─────────────────────────────────────

    def get_course_activities(self) -> list:
        """
        Сканирует страницу курса campus.fa.ru.
        Возвращает все тесты, видео, PDF, задания.
        """
        activities = []
        seen = set()

        all_links = self.page.query_selector_all(
            '.activityinstance a, '
            '.activity a.aalink, '
            'li.activity a[href*="/mod/"]'
        )

        for el in all_links:
            href = el.get_attribute("href") or ""
            if not href or href in seen:
                continue
            name = el.inner_text().strip() or el.get_attribute("title") or "Без названия"

            if "/mod/quiz/" in href:
                atype = "quiz"
            elif "/mod/url/" in href or "mts-link" in href:
                atype = "video"
            elif "/mod/resource/" in href:
                atype = "pdf"
            elif "/mod/assign/" in href:
                atype = "assignment"
            else:
                atype = "other"

            activities.append({"type": atype, "name": name, "url": href})
            seen.add(href)

        quizzes = sum(1 for a in activities if a["type"] == "quiz")
        print(f"  📋 Активностей: {len(activities)} (тестов: {quizzes})")
        return activities

    # ─── ТЕСТ ─────────────────────────────────────────────────

    def start_quiz(self) -> bool:
        btn = (
            self.page.query_selector('button:has-text("Начать тестирование")') or
            self.page.query_selector('a:has-text("Начать тестирование")') or
            self.page.query_selector('input[value="Начать тестирование"]')
        )
        if btn:
            btn.click()
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)
            confirm = self.page.query_selector('button:has-text("Начать попытку")')
            if confirm:
                confirm.click()
                self.page.wait_for_load_state("networkidle")
                time.sleep(2)
            print("✅ Тест начат")
            return True
        return False

    def get_quiz_data(self) -> list:
        questions = []
        question_blocks = self.page.query_selector_all(".que")

        for block in question_blocks:
            q_el = block.query_selector(".qtext")
            if not q_el:
                continue
            question_text = q_el.inner_text().strip()

            radios = block.query_selector_all('.answer input[type="radio"]')
            checkboxes = block.query_selector_all('.answer input[type="checkbox"]')
            text_input = block.query_selector('.answer input[type="text"]')

            if radios:
                labels = block.query_selector_all('.answer label')
                options = [l.inner_text().strip() for l in labels]
                questions.append({"question": question_text, "type": "radio",
                                   "options": options, "elements": list(radios)})
            elif checkboxes:
                labels = block.query_selector_all('.answer label')
                options = [l.inner_text().strip() for l in labels]
                questions.append({"question": question_text, "type": "checkbox",
                                   "options": options, "elements": list(checkboxes)})
            elif text_input:
                questions.append({"question": question_text, "type": "text",
                                   "options": [], "elements": [text_input]})

        print(f"  📋 Вопросов: {len(questions)}")
        return questions

    def click_answer(self, element):
        element.click()
        time.sleep(0.3)

    def submit_quiz(self):
        # ── ПАУЗА ДЛЯ ПРОВЕРКИ ──────────────────────────────────
        print("\n" + "="*50)
        print("⏸  ПАУЗА — агент подобрал ответы на все вопросы")
        print("   Проверь ответы в браузере и внеси правки если нужно")
        print("   Нажми Enter чтобы отправить, Ctrl+C чтобы отменить")
        input("="*50 + "\n> ")
        # ────────────────────────────────────────────────────────

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

        print("  ✅ Тест завершён")

    # ─── ЗАДАНИЯ ──────────────────────────────────────────────

    def get_task_text(self) -> str:
        task_el = (
            self.page.query_selector(".box.generalbox") or
            self.page.query_selector("#intro") or
            self.page.query_selector('[role="main"]')
        )
        if task_el:
            return task_el.inner_text().strip()
        return ""

    def fill_text_answer(self, text: str):
        iframe = self.page.query_selector('iframe[id*="id_introeditor"]')
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
        # ── ПАУЗА ДЛЯ ПРОВЕРКИ ──────────────────────────────────
        print("\n" + "="*50)
        print("⏸  ПАУЗА — черновик задания готов")
        print("   Прочитай текст в браузере, отредактируй если нужно")
        print("   Нажми Enter чтобы отправить, Ctrl+C чтобы отменить")
        input("="*50 + "\n> ")
        # ────────────────────────────────────────────────────────

        btn = (
            self.page.query_selector('input[value="Сохранить изменения"]') or
            self.page.query_selector('button:has-text("Сохранить")')
        )
        if btn:
            btn.click()
            self.page.wait_for_load_state("networkidle")
        print("  ✅ Задание отправлено")

    def close(self):
        self.browser.close()
        self.playwright.stop()


# ─── ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ──────────────────────────────────

def _is_academic_course(name: str) -> bool:
    """
    Фильтрует нерелевантные курсы.
    Пропускает: Бакалавриат (административный), системные разделы.
    """
    skip_keywords = ["бакалавриат", "административный", "институт открытого"]
    name_lower = name.lower()
    return not any(kw in name_lower for kw in skip_keywords)
