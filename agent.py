"""
agent.py — основной агент с полной функциональностью.
"""

import time
import os
import re
import hashlib
from datetime import datetime, timedelta

from subjects import SubjectRegistry, Subject, TeacherRegistry, Stats
from lecture_listener import LectureListener
from presence import PresenceKeeper
from smart_solver import SmartSolver
from essay_solver import EssaySolver
from browser import UniBrowser, EXTERNAL_DOMAINS
from telegram_notifier import TelegramNotifier
from quiz_digest import QuizDigest

NOTES_DIR = "notes"


class SubjectAgent:
    def __init__(self, subject: Subject):
        self.subject = subject
        self.registry = SubjectRegistry()
        self.tg = TelegramNotifier()
        self.stats = Stats()

    def _make_browser(self) -> UniBrowser:
        """Создаёт браузер для платформы предмета (campus или online.fa.ru)."""
        base_url = self.subject.source_platform or None
        return UniBrowser(headless=True, base_url=base_url)

    # ─── Лекция ────────────────────────────────────────────────

    def run_lecture(self, event_id: str = None, webinar_url: str = None):
        s = self.subject
        eid = event_id or (s.event_ids[-1] if s.event_ids else None)
        url = webinar_url or s.webinar_url

        if not eid:
            self.tg.notify(f"❌ [{s.name}] Не указан ID эфира")
            return None

        self.tg.notify(f"🎓 Начинаю лекцию: <b>{s.name}</b>")

        with PresenceKeeper(url):
            listener = LectureListener(eid)
            knowledge = listener.listen_realtime(s.duration_minutes)

        if knowledge.strip():
            os.makedirs(NOTES_DIR, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"{NOTES_DIR}/{s.subject_id}_{date_str}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Предмет: {s.name}\nДата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
                f.write(knowledge)
            self.registry.add_notes(s.subject_id, filename)
            words = len(knowledge.split())
            self.stats.record_lecture(s.subject_id, words)
            self.tg.notify_lecture_done(s.name, words)
            return filename
        else:
            self.tg.notify(f"⚠️ [{s.name}] Конспект пуст")
            return None

    # ─── Тесты ─────────────────────────────────────────────────

    def run_quiz_by_url(self, quiz_url: str, dry_run: bool = False):
        """
        Решает тест с подтверждением через Telegram.
        dry_run=True — только показывает ответы, не отправляет.
        """
        s = self.subject

        # Проверка флагов предмета
        if s.external_platform:
            self.tg.notify(f"🔗 [{s.name}] Курс на другой платформе — пропускаю")
            return
        if s.needs_enrollment:
            self.tg.notify(f"📝 [{s.name}] Нужна запись на курс — пропускаю")
            return

        # Проверка статуса теста
        if s.quiz_status.get(quiz_url) == "done":
            self.tg.notify(f"✅ [{s.name}] Тест уже сдан, пропускаю")
            return

        context = s.get_context_for_ai()
        solver = SmartSolver(context)

        self.tg.notify(f"📝 Открываю тест: <b>{s.name}</b>")
        bot = self._make_browser()

        try:
            bot.login()
            bot.goto(quiz_url)

            # Определяем состояние теста
            state_info = bot.get_quiz_state()
            state = state_info["state"]
            max_attempts = state_info["max_attempts"]

            if state == "done":
                self.tg.notify(f"✅ [{s.name}] Тест уже сдан: {state_info.get('grade', '')}")
                self.registry.set_quiz_status(s.subject_id, quiz_url, "done")
                return

            # Тест с одной попыткой — особое подтверждение
            if max_attempts == 1 and state == "new":
                quiz_name = bot.page.title().replace("Алгебра и анализ", "").strip()[:80]
                decision = self.tg.confirm_single_attempt_quiz(s.name, quiz_name, 1)
                if decision != "start":
                    self.tg.notify(f"⏭ [{s.name}] Тест пропущен")
                    return

            # Начинаем тест
            if not bot.start_quiz():
                self.tg.notify(f"⚠️ [{s.name}] Не смог начать тест")
                return

            questions = bot.get_quiz_data()
            if not questions:
                self.tg.notify(f"⚠️ [{s.name}] Вопросы не найдены")
                return

            self.registry.set_quiz_status(s.subject_id, quiz_url, "in_progress", max_attempts)

            answers, confidences = solver.solve_all(questions)

            # Вводим ответы
            for q, ans in zip(questions, answers):
                bot.fill_answer(q, ans)

            if dry_run:
                self.tg.confirm_quiz(s.name + " (DRY RUN)", questions, answers, confidences)
                self.tg.notify(f"🔍 [{s.name}] Dry-run завершён — тест НЕ отправлен")
                return

            result = self.tg.confirm_quiz(s.name, questions, answers, confidences)

            if result == "approve":
                bot.submit_quiz()
                grade = bot.get_quiz_grade()
                self.registry.set_quiz_status(s.subject_id, quiz_url, "done")
                self.stats.record_quiz(s.subject_id, "passed")
                grade_str = f"\nОценка: <b>{grade}</b>" if grade else ""
                self.tg.notify(f"✅ Тест сдан: <b>{s.name}</b>{grade_str}")

                # Генерируем дайджест и сохраняем как конспект
                try:
                    digest = QuizDigest(s.name)
                    digest_html = digest.generate(questions, answers, confidences, grade)
                    if digest_html:
                        self.tg.notify(digest_html)
                        digest_path = digest.save(s.subject_id, digest_html)
                        self.registry.add_notes(s.subject_id, digest_path)
                except Exception as digest_err:
                    print(f"  ⚠️ Дайджест не сгенерирован: {digest_err}")
            else:
                self.stats.record_quiz(s.subject_id, "skipped")
                self.tg.notify(f"⏭ Тест пропущен: <b>{s.name}</b>")

        except Exception as e:
            self.tg.notify_error(s.name, str(e))
        finally:
            bot.close()

    def run_quizzes(self, dry_run: bool = False):
        for quiz_url in self.subject.quiz_urls:
            self.run_quiz_by_url(quiz_url, dry_run=dry_run)
            time.sleep(3)

    # ─── Задания ───────────────────────────────────────────────

    def run_assignment_by_url(self, assignment_url: str, dry_run: bool = False):
        s = self.subject

        if s.external_platform or s.needs_enrollment:
            self.tg.notify(f"⚠️ [{s.name}] Пропускаю — особые условия")
            return

        if s.assignment_status.get(assignment_url) in ("submitted", "graded"):
            self.tg.notify(f"✅ [{s.name}] Задание уже сдано")
            return

        context = s.get_context_for_ai()
        essay_solver = EssaySolver(context)

        self.tg.notify(f"✍️ Открываю задание: <b>{s.name}</b>")
        bot = self._make_browser()

        try:
            bot.login()
            bot.goto(assignment_url)

            info = bot.get_assignment_info()
            task_text = info.get("task_text", "")
            deadline = info.get("deadline", "")

            if info.get("status") in ("submitted", "graded"):
                self.tg.notify(f"✅ [{s.name}] Уже сдано")
                self.registry.set_assignment_status(s.subject_id, assignment_url, info["status"])
                return

            if not task_text:
                self.tg.notify(f"⚠️ [{s.name}] Нет текста задания")
                return

            full_task = task_text
            if s.teacher_requirements.strip():
                full_task = f"ТРЕБОВАНИЯ К КУРСУ:\n{s.teacher_requirements[:2000]}\n\nЗАДАНИЕ:\n{task_text}"

            answer = essay_solver.write_essay(full_task)
            if not answer:
                self.tg.notify(f"⚠️ [{s.name}] Ответ не сгенерирован")
                return

            confidence = 0.8 if s.get_full_knowledge().strip() else 0.5

            if dry_run:
                self.tg.confirm_assignment(s.name + " (DRY RUN)", task_text, answer, confidence)
                self.tg.notify(f"🔍 [{s.name}] Dry-run — НЕ отправлено")
                return

            result = self.tg.confirm_assignment(s.name, task_text, answer, confidence)

            if result == "approve":
                bot.open_assignment_editor()
                time.sleep(1)
                bot.fill_text_answer(answer)
                time.sleep(1)
                bot.submit_assignment()
                self.registry.set_assignment_status(s.subject_id, assignment_url, "submitted", deadline)
                self.stats.record_assignment(s.subject_id)
                self.tg.notify(f"✅ Задание сдано: <b>{s.name}</b>")
            else:
                self.tg.notify(f"⏭ Задание пропущено: <b>{s.name}</b>")

        except Exception as e:
            self.tg.notify_error(s.name, str(e))
        finally:
            bot.close()

    def run_assignments(self, dry_run: bool = False):
        for url in self.subject.assignment_urls:
            self.run_assignment_by_url(url, dry_run=dry_run)
            time.sleep(3)

    def full_cycle(self, event_id: str = None, webinar_url: str = None):
        self.tg.notify(f"🚀 Начинаю цикл: <b>{self.subject.name}</b>")
        self.run_lecture(event_id, webinar_url)
        time.sleep(5)
        self.run_quizzes()
        self.run_assignments()
        self.tg.notify(f"✅ Цикл завершён: <b>{self.subject.name}</b>")


# ─── Утилиты ────────────────────────────────────────────────

def _slugify(name: str) -> str:
    cleaned = re.sub(r'[^a-zа-я0-9]', '_', name.lower())[:20]
    cleaned = re.sub(r'_+', '_', cleaned).strip('_') or "course"
    h = hashlib.md5(name.encode()).hexdigest()[:4]
    return f"{cleaned}_{h}"


def _is_real_course_name(name: str) -> bool:
    bad = ["изображение курса", "изображение", "image", "без названия"]
    return name.lower().strip() not in bad and len(name.strip()) >= 3


def _detect_semester(course_name: str) -> str:
    """Парсит '_1_сем' или '_2_сем' из названия курса."""
    m = re.search(r'_(\d)_сем', course_name)
    return m.group(1) if m else ""


# ─── Сканирование всех курсов ─────────────────────────────────

ONLINE_FA_URL = "https://online.fa.ru"


def scan_all_courses(current_semester: str = "2"):
    """
    Сканирует campus.fa.ru. Отмечает:
    - source_platform = online.fa.ru — если курс там (обрабатывается, не пропускается)
    - external_platform — если курс на Stepik/Coursera/etc. (пропускается)
    - completed — если курс не текущего семестра
    """
    tg = TelegramNotifier()
    registry = SubjectRegistry()
    teachers = TeacherRegistry()

    tg.notify(f"🔍 Сканирую курсы (текущий семестр: {current_semester})")

    bot = UniBrowser(headless=True)
    stats = {
        "courses": 0, "active": 0, "old_semester": 0, "external": 0,
        "quizzes": 0, "assignments": 0, "with_req": 0,
    }

    try:
        bot.login()
        courses = bot.get_my_courses()
        if not courses:
            tg.notify("⚠️ Курсы не найдены")
            return

        # Дедупликация — предпочитаем нормальные названия
        unique = {}
        for c in courses:
            url = c["url"]
            if url not in unique or (_is_real_course_name(c["name"]) and not _is_real_course_name(unique[url]["name"])):
                unique[url] = c
        courses = list(unique.values())

        tg.notify(f"📚 Уникальных курсов: <b>{len(courses)}</b>")

        for course in courses:
            name = course["name"]
            url = course["url"]

            # Если имя плохое — пытаемся получить настоящее из title страницы
            # (не пропускаем курс — сохраняем с временным именем)
            bad_initial_name = not _is_real_course_name(name)

            stats["courses"] += 1
            subject_id = _slugify(name if not bad_initial_name else f"course_{url.split('id=')[-1]}")

            subject = registry.get(subject_id)
            if not subject:
                subject = Subject(name=name, subject_id=subject_id)
                registry.add(subject)

            # Определяем семестр
            semester = _detect_semester(name)
            subject.semester = semester

            # Помечаем сданный если другой семестр
            if semester and semester != current_semester:
                subject.completed = True
                stats["old_semester"] += 1
                registry._save()
                print(f"  ⏭ {name} — семестр {semester}, пропускаю")
                continue

            stats["active"] += 1

            try:
                bot.goto(url)

                # Извлекаем требования преподавателя
                info = bot.get_course_info()

                # Настоящее название (из title страницы)
                if info.get("name") and _is_real_course_name(info["name"]):
                    subject.name = info["name"]

                if info.get("description"):
                    registry.update_requirements(
                        subject_id,
                        info["description"],
                        info.get("teacher_name", ""),
                        info.get("teacher_email", "")
                    )
                    stats["with_req"] += 1

                    # Добавляем в базу преподавателей
                    if info.get("teacher_name"):
                        teachers.add_or_update(
                            info["teacher_name"],
                            info.get("teacher_email", ""),
                            info["description"],
                            [subject.name]
                        )

                # Проверяем внешние ссылки
                external_links = info.get("external_links", [])
                if external_links:
                    online_links = [l for l in external_links if "online.fa.ru" in l]
                    other_links = [l for l in external_links if "online.fa.ru" not in l]

                    if online_links:
                        # online.fa.ru — тоже Moodle, бот умеет работать там
                        subject.source_platform = ONLINE_FA_URL
                        subject.external_url = online_links[0]
                        subject.external_platform = False
                        tg.notify(
                            f"🌐 <b>{subject.name}</b>\n"
                            f"Курс на online.fa.ru — добавлен в очередь сканирования"
                        )
                        registry._save()
                        # Курс будет просканирован через scan_online_fa_courses()
                        continue
                    elif other_links:
                        subject.external_platform = True
                        subject.external_url = other_links[0]
                        stats["external"] += 1
                        tg.notify(
                            f"🔗 <b>{subject.name}</b>\n"
                            f"Курс на неподдерживаемой платформе:\n"
                            f"<code>{other_links[0][:80]}</code>\n"
                            f"Помечен как external — бот пропускает"
                        )
                        registry._save()
                        continue

                # Собираем активности
                activities = bot.get_course_activities()
                for a in activities:
                    if a["type"] == "quiz" and a["url"] not in subject.quiz_urls:
                        subject.quiz_urls.append(a["url"])
                        stats["quizzes"] += 1
                    elif a["type"] == "assignment" and a["url"] not in subject.assignment_urls:
                        subject.assignment_urls.append(a["url"])
                        stats["assignments"] += 1
                    elif a["type"] == "video" and not subject.webinar_url:
                        subject.webinar_url = a["url"]

                registry._save()
                print(f"  [{subject.name[:40]}] т:{len([a for a in activities if a['type']=='quiz'])} з:{len([a for a in activities if a['type']=='assignment'])}")

            except Exception as e:
                print(f"  ⚠️ [{name}]: {e}")

        # Считаем предметы на online.fa.ru
        online_count = sum(
            1 for s in registry.all()
            if s.source_platform == ONLINE_FA_URL and not s.completed
        )
        tg.notify(
            f"✅ <b>Сканирование campus.fa.ru завершено</b>\n\n"
            f"Курсов: <b>{stats['courses']}</b>\n"
            f"Активных (сем. {current_semester}): <b>{stats['active']}</b>\n"
            f"Сдано (другой семестр): <b>{stats['old_semester']}</b>\n"
            f"Внешние (Stepik/etc.): <b>{stats['external']}</b>\n"
            f"На online.fa.ru: <b>{online_count}</b> — используй /scan_online\n"
            f"С требованиями преподавателя: <b>{stats['with_req']}</b>\n"
            f"Тестов: <b>{stats['quizzes']}</b>\n"
            f"Заданий: <b>{stats['assignments']}</b>"
        )

    except Exception as e:
        tg.notify_error("Сканирование", str(e))
    finally:
        bot.close()


def run_all_assignments(dry_run: bool = False):
    registry = SubjectRegistry()
    for subject in registry.all(active_only=True):
        if subject.assignment_urls:
            SubjectAgent(subject).run_assignments(dry_run=dry_run)


def run_all_quizzes(dry_run: bool = False):
    registry = SubjectRegistry()
    for subject in registry.all(active_only=True):
        if subject.quiz_urls:
            SubjectAgent(subject).run_quizzes(dry_run=dry_run)


def scan_online_fa_courses():
    """
    Сканирует курсы на online.fa.ru для предметов, у которых source_platform = ONLINE_FA_URL.
    Находит тесты и задания, сохраняет в реестр.
    """
    tg = TelegramNotifier()
    registry = SubjectRegistry()
    teachers = TeacherRegistry()

    online_subjects = [
        s for s in registry.all()
        if s.source_platform == ONLINE_FA_URL and not s.completed
    ]

    if not online_subjects:
        tg.notify("ℹ️ Нет предметов на online.fa.ru. Сначала запусти /scan")
        return

    tg.notify(f"🔍 Сканирую online.fa.ru: {len(online_subjects)} предметов")

    bot = UniBrowser(headless=True, base_url=ONLINE_FA_URL)
    stats = {"quizzes": 0, "assignments": 0, "errors": 0}

    try:
        bot.login()

        for subject in online_subjects:
            try:
                # Если есть прямая ссылка на курс — идём туда
                course_url = subject.external_url
                if not course_url:
                    print(f"  ⚠️ [{subject.name}] Нет ссылки на online.fa.ru, пропускаю")
                    continue

                bot.goto(course_url)

                # Обновляем название и требования
                info = bot.get_course_info()
                if info.get("name") and _is_real_course_name(info["name"]):
                    subject.name = info["name"]
                if info.get("description"):
                    registry.update_requirements(
                        subject.subject_id,
                        info["description"],
                        info.get("teacher_name", ""),
                        info.get("teacher_email", "")
                    )
                    if info.get("teacher_name"):
                        teachers.add_or_update(
                            info["teacher_name"],
                            info.get("teacher_email", ""),
                            info["description"],
                            [subject.name]
                        )

                # Собираем активности
                activities = bot.get_course_activities()
                new_q, new_a = 0, 0
                for a in activities:
                    if a["type"] == "quiz" and a["url"] not in subject.quiz_urls:
                        subject.quiz_urls.append(a["url"])
                        stats["quizzes"] += 1
                        new_q += 1
                    elif a["type"] == "assignment" and a["url"] not in subject.assignment_urls:
                        subject.assignment_urls.append(a["url"])
                        stats["assignments"] += 1
                        new_a += 1

                registry._save()
                print(f"  [{subject.name[:40]}] тестов: +{new_q}, заданий: +{new_a}")

            except Exception as e:
                stats["errors"] += 1
                print(f"  ⚠️ [{subject.name}]: {e}")

        tg.notify(
            f"✅ <b>Сканирование online.fa.ru завершено</b>\n\n"
            f"Предметов: <b>{len(online_subjects)}</b>\n"
            f"Тестов найдено: <b>{stats['quizzes']}</b>\n"
            f"Заданий найдено: <b>{stats['assignments']}</b>\n"
            f"Ошибок: <b>{stats['errors']}</b>"
        )

    except Exception as e:
        tg.notify_error("Сканирование online.fa.ru", str(e))
    finally:
        bot.close()


def get_upcoming_deadlines() -> list:
    """Читает календарь campus.fa.ru, возвращает предстоящие события."""
    bot = UniBrowser(headless=True)
    try:
        bot.login()
        return bot.get_upcoming_deadlines()
    finally:
        bot.close()
