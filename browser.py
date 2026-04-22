"""
browser.py — управление браузером для campus.fa.ru (Moodle).
С расширенной диагностикой и обходом всех секций курса.
"""

import os
import time
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()


class UniBrowser:
    def __init__(self, headless: bool = True):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    # ─── Авторизация ──────────────────────────────────────────

    def login(self):
        uni_url = os.getenv("UNI_URL", "https://campus.fa.ru/login/index.php")
        login_val = os.getenv("UNI_LOGIN")
        password_val = os.getenv("UNI_PASSWORD")

        if not login_val or not password_val:
            raise ValueError("UNI_LOGIN или UNI_PASSWORD не заданы")

        print(f"🔐 Открываю страницу логина: {uni_url}")
        self.page.goto(uni_url, timeout=60000)
        self.page.wait_for_load_state("networkidle")

        username_field = (
            self.page.query_selector('input[name="username"]') or
            self.page.query_selector('input[id="username"]') or
            self.page.query_selector('input[type="text"]')
        )
        password_field = (
            self.page.query_selector('input[name="password"]') or
            self.page.query_selector('input[id="password"]') or
            self.page.query_selector('input[type="password"]')
        )

        if not username_field or not password_field:
            raise RuntimeError("Не нашёл поля логина на странице")

        username_field.fill(login_val)
        password_field.fill(password_val)

        submit_btn = (
            self.page.query_selector('#loginbtn') or
            self.page.query_selector('button[type="submit"]') or
            self.page.query_selector('input[type="submit"]')
        )
        if submit_btn:
            submit_btn.click()

        self.page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)

        current_url = self.page.url
        print(f"📍 URL после логина: {current_url}")

        if "login" in current_url.lower():
            error_el = (
                self.page.query_selector('.loginerrors') or
                self.page.query_selector('.alert-danger') or
                self.page.query_selector('.error')
            )
            err_text = error_el.inner_text().strip() if error_el else "неизвестная причина"
            raise RuntimeError(f"Логин не прошёл: {err_text}")

        print("✅ Авторизация успешна")

    def goto(self, url: str):
        self.page.goto(url, timeout=60000)
        self.page.wait_for_load_state("networkidle")
        time.sleep(2)

    # ─── Поиск курсов (расширенный) ──────────────────────────

    def get_my_courses(self) -> list:
        """
        Собирает список курсов студента со всех возможных страниц.
        """
        uni_url = os.getenv("UNI_URL", "https://campus.fa.ru")
        base = uni_url.split("/login")[0].rstrip("/")

        all_courses = {}

        urls_to_scan = [
            f"{base}/my/courses.php",
            f"{base}/my/",
            f"{base}/",
            f"{base}/course/index.php",
        ]

        for url in urls_to_scan:
            try:
                print(f"🔍 Сканирую: {url}")
                self.page.goto(url, timeout=60000)
                self.page.wait_for_load_state("networkidle")
                time.sleep(3)

                if "login" in self.page.url.lower() and url not in self.page.url:
                    print("   ⚠️ Сброшена сессия")
                    continue

                selectors = [
                    'a[href*="/course/view.php"]',
                    '.coursename a',
                    '.course-info-container a',
                    '[data-region="course-content"] a',
                    '.courses .course a',
                ]

                found = 0
                for selector in selectors:
                    for el in self.page.query_selector_all(selector):
                        href = el.get_attribute("href") or ""
                        if "/course/view.php" not in href:
                            continue

                        name = el.inner_text().strip()
                        if not name:
                            name = (
                                el.get_attribute("title") or
                                el.get_attribute("aria-label") or
                                ""
                            ).strip()

                        if href and name and href not in all_courses:
                            all_courses[href] = {"name": name, "url": href}
                            found += 1

                print(f"   Новых курсов: {found}")

            except Exception as e:
                print(f"   ⚠️ Ошибка: {e}")
                continue

        courses = list(all_courses.values())
        print(f"\n📚 Всего курсов: {len(courses)}")

        for c in courses[:10]:
            print(f"   • {c['name'][:70]}")
        if len(courses) > 10:
            print(f"   ... и ещё {len(courses) - 10}")

        return courses

    # ─── Материалы внутри курса ──────────────────────────────

    def get_course_activities(self) -> list:
        """
        Сканирует страницу курса — все секции на одной странице.
        Собирает тесты, задания, видео, файлы.
        """
        activities = []
        seen = set()

        time.sleep(2)

        # Раскрываем свёрнутые секции
        try:
            collapsed = self.page.query_selector_all(
                '[aria-expanded="false"], .collapsed .sectionname a'
            )
            for c in collapsed[:20]:
                try:
                    c.click()
                    time.sleep(0.2)
                except Exception:
                    pass
        except Exception:
            pass

        selectors = [
            '.activityinstance a',
            '.activity a.aalink',
            'li.activity a[href*="/mod/"]',
            'a[href*="/mod/quiz/"]',
            'a[href*="/mod/assign/"]',
            'a[href*="/mod/resource/"]',
            'a[href*="/mod/url/"]',
            'a[href*="/mod/page/"]',
            'a[href*="/mod/forum/"]',
            'a[href*="/mod/lesson/"]',
        ]

        for selector in selectors:
            for el in self.page.query_selector_all(selector):
                href = el.get_attribute("href") or ""
                if not href or href in seen or "/mod/" not in href:
                    continue

                name = el.inner_text().strip()
                if not name:
                    name = el.get_attribute("title") or "Без названия"

                if "/mod/quiz/" in href:
                    atype = "quiz"
                elif "/mod/assign/" in href:
                    atype = "assignment"
                elif "/mod/url/" in href or "mts-link" in href or "webinar.ru" in href:
                    atype = "video"
                elif "/mod/resource/" in href:
                    atype = "pdf"
                elif "/mod/lesson/" in href:
                    atype = "lesson"
                else:
                    atype = "other"

                activities.append({"type": atype, "name": name, "url": href})
                seen.add(href)

        # Прямые ссылки на эфиры в контенте
        for el in self.page.query_selector_all('a[href*="mts-link.ru"], a[href*="webinar.ru"]'):
            href = el.get_attribute("href") or ""
            if href and href not in seen:
                name = el.inner_text().strip() or "Эфир"
                activities.append({"type": "video", "name": name, "url": href})
                seen.add(href)

        types_count = {}
        for a in activities:
            types_count[a["type"]] = types_count.get(a["type"], 0) + 1
        print(f"   📋 Материалов: {len(activities)} — {types_count}")

        return activities

    # ─── Тесты ────────────────────────────────────────────────

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
        for block in self.page.query_selector_all(".que"):
            q_el = block.query_selector(".qtext")
            if not q_el:
                continue
            question_text = q_el.inner_text().strip()

            radios = block.query_selector_all('.answer input[type="radio"]')
            checkboxes = block.query_selector_all('.answer input[type="checkbox"]')

            if radios:
                labels = block.query_selector_all('.answer label')
                options = [l.inner_text().strip() for l in labels]
                questions.append({
                    "question": question_text, "type": "radio",
                    "options": options, "elements": list(radios)
                })
            elif checkboxes:
                labels = block.query_selector_all('.answer label')
                options = [l.inner_text().strip() for l in labels]
                questions.append({
                    "question": question_text, "type": "checkbox",
                    "options": options, "elements": list(checkboxes)
                })

        print(f"  📋 Вопросов найдено: {len(questions)}")
        return questions

    def click_answer(self, element):
        try:
            element.click()
            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠️ Не смог кликнуть: {e}")

    def submit_quiz(self):
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

        print("  ✅ Тест отправлен")

    # ─── Задания ──────────────────────────────────────────────

    def get_task_text(self) -> str:
        task_el = (
            self.page.query_selector(".box.generalbox") or
            self.page.query_selector("#intro") or
            self.page.query_selector('[role="main"]')
        )
        if task_el:
            text = task_el.inner_text().strip()
            print(f"📄 Прочитано требований: {len(text)} симв.")
            return text
        return ""

    def open_assignment_editor(self):
        btn = (
            self.page.query_selector('button:has-text("Добавить ответ")') or
            self.page.query_selector('a:has-text("Добавить ответ")') or
            self.page.query_selector('input[value*="ответ"]')
        )
        if btn:
            btn.click()
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)
            return True
        return False

    def fill_text_answer(self, text: str):
        iframe = self.page.query_selector('iframe[id*="editor"], iframe.cke_wysiwyg_frame')
        if iframe:
            frame = iframe.content_frame()
            if frame:
                body = frame.query_selector("body")
                if body:
                    body.fill(text)
                    print("✅ Ответ вставлен в iframe")
                    return

        textarea = self.page.query_selector("textarea")
        if textarea:
            textarea.fill(text)
            print("✅ Ответ вставлен в textarea")
            return

        editable = self.page.query_selector('[contenteditable="true"]')
        if editable:
            editable.click()
            editable.fill(text)
            print("✅ Ответ вставлен в contenteditable")

    def submit_assignment(self):
        btn = (
            self.page.query_selector('input[value="Сохранить изменения"]') or
            self.page.query_selector('button:has-text("Сохранить")') or
            self.page.query_selector('button[type="submit"]')
        )
        if btn:
            btn.click()
            self.page.wait_for_load_state("networkidle")
            print("  ✅ Задание сохранено")

    def close(self):
        try:
            self.context.close()
            self.browser.close()
            self.playwright.stop()
        except Exception:
            pass
