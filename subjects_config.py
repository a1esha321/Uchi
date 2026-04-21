"""
subjects_config.py — список всех предметов и их расписание.

⚠️ НАСТРОЙ: заполни своими предметами, ссылками и расписанием.
"""

# Каждый предмет — это словарь с параметрами
SUBJECTS = {

    "marketing": {
        "name": "Маркетинг",
        "webinar_url": "https://events.mts-link.ru/ЗАМЕНИ",
        "event_id": "ЗАМЕНИ",
        "quiz_url": "https://университет.ru/quiz/marketing",
        "assignment_url": "https://университет.ru/assignment/marketing",
        "duration_minutes": 90,
        # Расписание: день недели + время (МСК)
        "schedule": {"day": "mon", "hour": 10, "minute": 0},
        # Папка где хранятся конспекты этого предмета
        "notes_dir": "notes/marketing/",
    },

    "law": {
        "name": "Право",
        "webinar_url": "https://events.mts-link.ru/ЗАМЕНИ",
        "event_id": "ЗАМЕНИ",
        "quiz_url": "https://университет.ru/quiz/law",
        "assignment_url": "https://университет.ru/assignment/law",
        "duration_minutes": 90,
        "schedule": {"day": "tue", "hour": 14, "minute": 0},
        "notes_dir": "notes/law/",
    },

    "economics": {
        "name": "Экономика",
        "webinar_url": "https://events.mts-link.ru/ЗАМЕНИ",
        "event_id": "ЗАМЕНИ",
        "quiz_url": "https://университет.ru/quiz/economics",
        "assignment_url": None,  # нет теста — только лекция
        "duration_minutes": 60,
        "schedule": {"day": "wed", "hour": 10, "minute": 0},
        "notes_dir": "notes/economics/",
    },

    "management": {
        "name": "Менеджмент",
        "webinar_url": "https://events.mts-link.ru/ЗАМЕНИ",
        "event_id": "ЗАМЕНИ",
        "quiz_url": "https://университет.ru/quiz/management",
        "assignment_url": "https://университет.ru/assignment/management",
        "duration_minutes": 90,
        "schedule": {"day": "thu", "hour": 16, "minute": 0},
        "notes_dir": "notes/management/",
    },

    # --- ДОБАВЛЯЙ СЮДА ОСТАЛЬНЫЕ ПРЕДМЕТЫ ПО АНАЛОГИИ ---
    # "subject_key": {
    #     "name": "Название предмета",
    #     "webinar_url": "...",
    #     "event_id": "...",
    #     "quiz_url": "...",      # или None
    #     "assignment_url": "...", # или None
    #     "duration_minutes": 90,
    #     "schedule": {"day": "fri", "hour": 10, "minute": 0},
    #     "notes_dir": "notes/subject_key/",
    # },
}
