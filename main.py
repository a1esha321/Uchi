"""
main.py — главный файл агента.

Запуск вручную (для теста):
    python main.py

Для автозапуска по расписанию используй scheduler.py
"""

import time
from lecture_listener import LectureListener
from presence import PresenceKeeper
from smart_solver import SmartSolver
from browser import UniBrowser


def attend_lecture_and_pass_quiz(
    webinar_url: str,
    event_id: str,
    quiz_url: str = None,
    duration_minutes: int = 90,
    subject_key: str = None,
):
    """
    Полный цикл учёбы:
    1. Заходим на эфир (фиксируем присутствие)
    2. Слушаем лекцию и накапливаем конспект
    3. Сохраняем конспект в папку предмета
    4. Решаем тест на основе лекции (если есть)

    Параметры:
        webinar_url      — ссылка на эфир МТС Линк
        event_id         — ID эфира (из URL)
        quiz_url         — ссылка на тест после лекции (или None)
        duration_minutes — длительность лекции в минутах
        subject_key      — ключ предмета из subjects_config.py (для сохранения в нужную папку)
    """

    print("\n" + "=" * 50)
    print("🎓 АГЕНТ ЗАПУЩЕН")
    print("=" * 50)

    # ШАГ 1: Фиксируем присутствие на эфире
    print("\n[1/4] Подключаюсь к эфиру...")
    presence = PresenceKeeper(webinar_url)
    presence.start()
    time.sleep(3)  # даём время открыться странице

    # ШАГ 2: Слушаем лекцию
    print(f"\n[2/4] Слушаю лекцию ({duration_minutes} мин)...")
    listener = LectureListener(event_id)
    knowledge = listener.listen_realtime(duration_minutes)

    # ШАГ 3: Останавливаем присутствие и сохраняем конспект
    print("\n[3/4] Сохраняю конспект...")
    presence.stop()

    if subject_key:
        from subject_manager import SubjectManager
        mgr = SubjectManager()
        notes_file = mgr.save_notes(subject_key, knowledge)
    else:
        notes_file = listener.save_notes()

    # Выводим резюме лекции
    if knowledge.strip():
        solver = SmartSolver(knowledge)
        summary = solver.make_summary()
        print("\n📋 РЕЗЮМЕ ЛЕКЦИИ:")
        print("-" * 40)
        print(summary)
        print("-" * 40)
    else:
        print("⚠️ Конспект пуст — возможно субтитры недоступны на твоём тарифе МТС Линк")
        solver = None

    # ШАГ 4: Решаем тест (если указан)
    if quiz_url and solver:
        print(f"\n[4/4] Решаю тест: {quiz_url}")
        time.sleep(5)

        bot = UniBrowser(headless=False)  # False — видишь что происходит
        try:
            bot.login()
            bot.goto(quiz_url)

            # Нажимаем "Начать тест" если есть такая кнопка
            start_btn = bot.page.query_selector('button:has-text("Начать")')
            if start_btn:
                start_btn.click()
                time.sleep(2)

            questions = bot.get_quiz_data()

            if not questions:
                print("⚠️ Вопросы не найдены. Проверь селекторы в browser.py")
            else:
                answers = solver.solve_all(questions)

                print("\n🖱️  Выбираю ответы...")
                for q, ans_idx in zip(questions, answers):
                    bot.click_answer(q["elements"][ans_idx])

                time.sleep(2)
                bot.submit_quiz()
                print("🎉 Тест сдан на основе знаний с лекции!")

        except Exception as e:
            print(f"❌ Ошибка при прохождении теста: {e}")
        finally:
            bot.close()

    elif quiz_url and not solver:
        print("\n⚠️ Тест пропущен — нет данных из лекции для обучения")
    else:
        print("\n[4/4] Тест не указан, завершаю работу")

    print("\n" + "=" * 50)
    print(f"✅ ГОТОВО. Конспект: {notes_file}")
    print("=" * 50 + "\n")


def do_essay_assignment(
    assignment_url: str,
    notes_file: str = None,
    lecture_knowledge: str = ""
):
    """
    Читает задание преподавателя со страницы и выполняет его.

    Параметры:
        assignment_url  — ссылка на страницу задания
        notes_file      — путь к файлу конспекта (например "notes_12345.txt")
        lecture_knowledge — или передай конспект напрямую строкой
    """
    from essay_solver import EssaySolver

    # Загружаем конспект из файла если указан
    if notes_file and not lecture_knowledge:
        try:
            with open(notes_file, "r", encoding="utf-8") as f:
                lecture_knowledge = f.read()
            print(f"📚 Загружен конспект из {notes_file}")
        except FileNotFoundError:
            print(f"⚠️ Файл конспекта не найден: {notes_file}")

    print("\n" + "=" * 50)
    print("✍️  ВЫПОЛНЯЮ ТЕКСТОВОЕ ЗАДАНИЕ")
    print("=" * 50)

    bot = UniBrowser(headless=False)
    try:
        # 1. Логин и переход к заданию
        bot.login()
        bot.goto(assignment_url)

        # 2. Читаем требования преподавателя
        task_text = bot.get_task_text()
        if not task_text:
            print("❌ Не удалось прочитать задание")
            return

        print(f"\n📋 Задание:\n{task_text[:300]}...\n")

        # 3. Claude пишет ответ
        solver = EssaySolver(lecture_knowledge)
        answer = solver.write_essay(task_text)

        print(f"\n📝 Написанный ответ:\n{'-'*40}\n{answer[:500]}...\n{'-'*40}")

        # 4. Вставляем ответ в поле
        bot.fill_text_answer(answer)
        time.sleep(1)

        # 5. Отправляем
        bot.submit_assignment()
        print("🎉 Задание выполнено и отправлено!")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        bot.close()


# ============================================================
# РУЧНОЙ ЗАПУСК ДЛЯ ТЕСТА
# Замени значения на свои и запусти: python main.py
# ============================================================
if __name__ == "__main__":

    # --- Вариант 1: посетить лекцию и сдать тест ---
    # attend_lecture_and_pass_quiz(
    #     webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    #     event_id="ЗАМЕНИ",
    #     quiz_url="https://университет.ru/quiz/ЗАМЕНИ",
    #     duration_minutes=90
    # )

    # --- Вариант 2: выполнить текстовое задание ---
    do_essay_assignment(
        assignment_url="https://университет.ru/assignment/ЗАМЕНИ",
        notes_file="notes_ЗАМЕНИ.txt",  # конспект лекции (или None)
    )
