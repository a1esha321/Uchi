"""
setup_subjects.py — реальные предметы из campus.fa.ru.

Запусти один раз в начале семестра:
    python setup_subjects.py
"""

from subjects import SubjectRegistry, Subject

registry = SubjectRegistry()

# ──────────────────────────────────────────────────────────
# 1 СЕМЕСТР — активные курсы (уже идут, есть оценки)
# ──────────────────────────────────────────────────────────

registry.add(Subject(
    name="Алгебра и анализ (1 сем)",
    subject_id="algebra_1",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",  # ← вставь ID эфира
    event_ids=[],
    quiz_urls=[],       # ← заполнится автоматически через navigator
    assignment_urls=[],
    schedule=[{"day": "mon", "hour": 10, "minute": 0}],  # ← замени время
    duration_minutes=90,
))

registry.add(Subject(
    name="Безопасность жизнедеятельности (1 сем)",
    subject_id="bgd_1",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    event_ids=[],
    quiz_urls=[],
    assignment_urls=[],
    schedule=[{"day": "tue", "hour": 10, "minute": 0}],
    duration_minutes=90,
))

registry.add(Subject(
    name="Дискретная математика (1 сем)",
    subject_id="discmath_1",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    event_ids=[],
    quiz_urls=[],
    assignment_urls=[],
    schedule=[{"day": "tue", "hour": 14, "minute": 0}],
    duration_minutes=90,
))

registry.add(Subject(
    name="Иностранный язык (1 сем)",
    subject_id="english_1",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    event_ids=[],
    quiz_urls=[],
    assignment_urls=[],
    schedule=[{"day": "wed", "hour": 10, "minute": 0}],
    duration_minutes=90,
))

registry.add(Subject(
    name="История России (1 сем)",
    subject_id="history_1",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    event_ids=[],
    quiz_urls=[],
    assignment_urls=[],
    schedule=[{"day": "wed", "hour": 14, "minute": 0}],
    duration_minutes=90,
))

registry.add(Subject(
    name="Практикум по программированию (1 сем)",
    subject_id="programming_1",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    event_ids=[],
    quiz_urls=[],
    assignment_urls=[],
    schedule=[{"day": "thu", "hour": 10, "minute": 0}],
    duration_minutes=90,
))

registry.add(Subject(
    name="Основы российской государственности (1 сем)",
    subject_id="orf_1",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    event_ids=[],
    quiz_urls=[],
    assignment_urls=[],
    schedule=[{"day": "fri", "hour": 10, "minute": 0}],
    duration_minutes=90,
))

registry.add(Subject(
    name="Физическая культура и спорт (1 сем)",
    subject_id="sport_1",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    event_ids=[],
    quiz_urls=[],
    assignment_urls=[],
    schedule=[{"day": "fri", "hour": 14, "minute": 0}],
    duration_minutes=60,
))

registry.add(Subject(
    name="Финансовый университет: история и современность (1 сем)",
    subject_id="finuniv_1",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    event_ids=[],
    quiz_urls=[],
    assignment_urls=[],
    schedule=[],  # онлайн курс, без расписания
    duration_minutes=60,
))

# ──────────────────────────────────────────────────────────
# 2 СЕМЕСТР — добавятся позже
# ──────────────────────────────────────────────────────────

registry.add(Subject(
    name="Алгоритмы и структуры данных Python (2 сем)",
    subject_id="python_2",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    event_ids=[],
    quiz_urls=[],
    assignment_urls=[],
    schedule=[],
    duration_minutes=90,
))

registry.add(Subject(
    name="Теория вероятностей и математическая статистика (2 сем)",
    subject_id="probability_2",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    event_ids=[],
    quiz_urls=[],
    assignment_urls=[],
    schedule=[],
    duration_minutes=90,
))

registry.add(Subject(
    name="Технологии обработки данных (2 сем)",
    subject_id="data_2",
    webinar_url="https://events.mts-link.ru/ЗАМЕНИ",
    event_ids=[],
    quiz_urls=[],
    assignment_urls=[],
    schedule=[],
    duration_minutes=90,
))

# ──────────────────────────────────────────────────────────

registry.print_all()

# Показываем что требует внимания (низкие оценки)
print("\n⚠️  ТРЕБУЮТ ВНИМАНИЯ (низкие оценки):")
print("  Алгебра и анализ       — 50.0")
print("  Практикум по прогр.    — 54.0")
print("  Иностранный язык       — 55.5")
print("  Дискретная математика  — 60.0")
print("  Осн. рос. государств.  — 0.0  ← КРИТИЧНО")
print("\n✅ Предметы сохранены в subjects.json")
print("   Следующий шаг: добавь ID эфиров МТС Линк и запусти scheduler.py")
