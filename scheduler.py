"""
scheduler.py — автоматический планировщик на основе subjects.json.

Читает расписание из реестра предметов и запускает агента
в нужное время для каждого предмета.

Запуск:
    python scheduler.py
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from subjects import SubjectRegistry
from agent import SubjectAgent
import logging

logging.basicConfig(
    filename="scheduler.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

scheduler = BlockingScheduler(timezone="Europe/Moscow")
registry = SubjectRegistry()

DAY_MAP = {
    "mon": "Понедельник", "tue": "Вторник", "wed": "Среда",
    "thu": "Четверг", "fri": "Пятница", "sat": "Суббота", "sun": "Воскресенье"
}


def make_job(subject):
    """Создаём функцию-задачу для конкретного предмета"""
    def job():
        print(f"\n⏰ Плановый запуск: {subject.name}")
        agent = SubjectAgent(subject)
        agent.full_cycle()
    job.__name__ = f"job_{subject.subject_id}"
    return job


# Регистрируем задачи для всех предметов из реестра
print("\n📅 РАСПИСАНИЕ:")
print("=" * 50)

for subject in registry.all():
    for slot in subject.schedule:
        day = slot["day"]
        hour = slot["hour"]
        minute = slot["minute"]

        scheduler.add_job(
            make_job(subject),
            trigger="cron",
            day_of_week=day,
            hour=hour,
            minute=minute,
            id=f"{subject.subject_id}_{day}_{hour}_{minute}"
        )

        print(f"  {DAY_MAP.get(day, day)} {hour:02d}:{minute:02d} → {subject.name}")

print("=" * 50)
print(f"Всего предметов: {len(registry.all())}")
print("\n⏰ Планировщик запущен. Ожидаю расписания...")
print("   Для остановки: Ctrl+C\n")

scheduler.start()


# ─── ЕЖЕНЕДЕЛЬНЫЙ АВТОНОМНЫЙ ОБХОД ────────────────────────────
# Каждое воскресенье в 20:00 агент сам обходит весь сайт
# и решает все найденные новые задания и тесты

@scheduler.scheduled_job('cron', day_of_week='sun', hour=20, minute=0, id='weekly_scan')
def weekly_full_scan():
    """Полный автономный обход сайта раз в неделю"""
    from navigator import Navigator
    print("\n🔍 Запускаю еженедельный обход сайта...")
    nav = Navigator(headless=True)
    nav.run_full_scan()
