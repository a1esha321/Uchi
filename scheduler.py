"""
scheduler.py — запускает агента по расписанию.
Читает расписание из subjects.json.
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from subjects import SubjectRegistry
from agent import SubjectAgent
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

scheduler = BlockingScheduler(timezone="Europe/Moscow")
registry = SubjectRegistry()

DAY_MAP = {
    "mon": "Пн", "tue": "Вт", "wed": "Ср",
    "thu": "Чт", "fri": "Пт", "sat": "Сб", "sun": "Вс"
}


def make_job(subject):
    def job():
        print(f"\nЗапуск: {subject.name}")
        agent = SubjectAgent(subject)
        agent.full_cycle()
    job.__name__ = f"job_{subject.subject_id}"
    return job


print("\n=== РАСПИСАНИЕ ===")
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
        print(f"  {DAY_MAP.get(day, day)} {hour:02d}:{minute:02d} -> {subject.name}")

if not registry.all():
    print("  Предметов нет. Запусти setup_subjects.py")

print("==================")
print("Планировщик запущен. Ожидаю расписания...\n")

scheduler.start()
