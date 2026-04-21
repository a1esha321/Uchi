"""
subject_manager.py — менеджер предметов.

Каждый предмет имеет свою отдельную "память" (папку с конспектами).
Менеджер знает какой предмет сейчас идёт и загружает нужные знания.
"""

import os
import glob
from datetime import datetime
from subjects_config import SUBJECTS


class SubjectManager:
    def __init__(self):
        # Создаём папки для конспектов всех предметов
        for key, subject in SUBJECTS.items():
            os.makedirs(subject["notes_dir"], exist_ok=True)
        print(f"📚 Загружено предметов: {len(SUBJECTS)}")

    def get_subject(self, subject_key: str) -> dict:
        """Возвращает конфиг предмета по ключу"""
        if subject_key not in SUBJECTS:
            raise ValueError(f"Предмет '{subject_key}' не найден в subjects_config.py")
        return SUBJECTS[subject_key]

    def save_notes(self, subject_key: str, content: str) -> str:
        """
        Сохраняет конспект лекции в папку предмета.
        Каждая лекция — отдельный файл с датой.
        """
        subject = self.get_subject(subject_key)
        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"{subject['notes_dir']}lecture_{date_str}.txt"

        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"Предмет: {subject['name']}\n")
            f.write(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
            f.write("=" * 50 + "\n\n")
            f.write(content)

        print(f"💾 Конспект сохранён: {filename}")
        return filename

    def load_all_notes(self, subject_key: str) -> str:
        """
        Загружает ВСЕ конспекты по предмету — накопленные за весь семестр.
        Чем больше лекций прослушано — тем глубже знания.
        """
        subject = self.get_subject(subject_key)
        notes_files = sorted(glob.glob(f"{subject['notes_dir']}*.txt"))

        if not notes_files:
            print(f"📭 Конспектов по '{subject['name']}' пока нет")
            return ""

        all_notes = []
        for filepath in notes_files:
            with open(filepath, "r", encoding="utf-8") as f:
                all_notes.append(f.read())

        combined = "\n\n" + "="*50 + "\n\n".join(all_notes)
        total_words = len(combined.split())
        print(f"📚 Загружено {len(notes_files)} конспектов по '{subject['name']}' ({total_words} слов)")
        return combined

    def load_latest_notes(self, subject_key: str) -> str:
        """Загружает только последний конспект (последняя лекция)"""
        subject = self.get_subject(subject_key)
        notes_files = sorted(glob.glob(f"{subject['notes_dir']}*.txt"))

        if not notes_files:
            return ""

        with open(notes_files[-1], "r", encoding="utf-8") as f:
            return f.read()

    def get_stats(self) -> str:
        """Показывает статистику по всем предметам"""
        lines = ["\n📊 СТАТИСТИКА ПО ПРЕДМЕТАМ", "=" * 40]

        for key, subject in SUBJECTS.items():
            notes_files = glob.glob(f"{subject['notes_dir']}*.txt")
            count = len(notes_files)
            status = f"✅ {count} лекций" if count > 0 else "⏳ Ещё не было лекций"
            lines.append(f"  {subject['name']}: {status}")

        lines.append("=" * 40)
        return "\n".join(lines)

    def list_subjects(self):
        """Выводит список всех предметов"""
        print("\n📋 ПРЕДМЕТЫ В ЭТОМ СЕМЕСТРЕ:")
        for key, subject in SUBJECTS.items():
            sched = subject["schedule"]
            days = {"mon":"Пн","tue":"Вт","wed":"Ср","thu":"Чт","fri":"Пт","sat":"Сб","sun":"Вс"}
            day_ru = days.get(sched["day"], sched["day"])
            print(f"  [{key}] {subject['name']} — {day_ru} {sched['hour']}:{sched['minute']:02d}")
