"""
setup_subjects.py — настройка предметов семестра.
Запусти один раз: python setup_subjects.py

После этого все предметы сохранятся в subjects.json
"""

from subjects import SubjectRegistry, Subject

registry = SubjectRegistry()

# ЗАПОЛНИ СВОИ ПРЕДМЕТЫ НИЖЕ
# Скопируй блок Subject(...) для каждого предмета

registry.add(Subject(
    name="Маркетинг",
    subject_id="marketing",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    event_ids=[],
    quiz_urls=["https://университет.ru/quiz/101"],
    assignment_urls=[],
    schedule=[{"day": "mon", "hour": 10, "minute": 0}],
    duration_minutes=90,
))

registry.add(Subject(
    name="Экономика",
    subject_id="economics",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    event_ids=[],
    quiz_urls=["https://университет.ru/quiz/102"],
    assignment_urls=[],
    schedule=[{"day": "tue", "hour": 12, "minute": 0}],
    duration_minutes=90,
))

# Добавь остальные предметы по аналогии...

print("\nПредметы сохранены в subjects.json")
print("Теперь запусти: python scheduler.py")
