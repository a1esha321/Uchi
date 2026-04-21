"""
subjects.py — реестр предметов.

Каждый предмет хранит:
- свои конспекты лекций (накапливаются весь семестр)
- расписание
- ссылки на тесты и задания

Конспекты сохраняются в папку notes/ и накапливаются от лекции к лекции.
"""

import os
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime


NOTES_DIR = "notes"
REGISTRY_FILE = "subjects.json"


@dataclass
class Subject:
    name: str               # Название предмета
    subject_id: str         # Короткий ID, например "marketing"
    webinar_url: str        # Ссылка на эфир МТС Линк
    event_ids: list         # Список ID всех эфиров (пополняется)
    quiz_urls: list         # Ссылки на тесты
    assignment_urls: list   # Ссылки на задания
    schedule: list          # Расписание: [{"day": "mon", "hour": 10, "minute": 0}]
    duration_minutes: int   # Длительность лекции в минутах
    notes_files: list = field(default_factory=list)  # Все конспекты этого предмета

    def get_full_knowledge(self) -> str:
        """
        Читает ВСЕ накопленные конспекты по предмету и объединяет.
        Чем больше лекций прослушано — тем глубже знания.
        """
        all_notes = []

        for filepath in self.notes_files:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    all_notes.append(content)

        if not all_notes:
            return ""

        combined = "\n\n---\n\n".join(all_notes)
        total_words = len(combined.split())
        print(f"📚 [{self.name}] Загружено {len(all_notes)} конспектов, {total_words} слов")
        return combined

    def add_notes_file(self, filepath: str):
        """Добавляем новый конспект к предмету"""
        if filepath not in self.notes_files:
            self.notes_files.append(filepath)


class SubjectRegistry:
    """
    Хранит все предметы семестра.
    Автоматически сохраняет и загружает из subjects.json.
    """

    def __init__(self):
        os.makedirs(NOTES_DIR, exist_ok=True)
        self.subjects: dict[str, Subject] = {}
        self._load()

    def add(self, subject: Subject):
        """Добавить предмет"""
        self.subjects[subject.subject_id] = subject
        self._save()
        print(f"✅ Добавлен предмет: {subject.name}")

    def get(self, subject_id: str) -> Subject:
        """Получить предмет по ID"""
        return self.subjects.get(subject_id)

    def all(self) -> list[Subject]:
        """Все предметы"""
        return list(self.subjects.values())

    def add_notes(self, subject_id: str, notes_file: str):
        """Добавить конспект к предмету и сохранить"""
        subject = self.get(subject_id)
        if subject:
            subject.add_notes_file(notes_file)
            self._save()

    def _save(self):
        data = {sid: asdict(s) for sid, s in self.subjects.items()}
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not os.path.exists(REGISTRY_FILE):
            return
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for sid, sdata in data.items():
            self.subjects[sid] = Subject(**sdata)
        print(f"📖 Загружено предметов: {len(self.subjects)}")

    def print_all(self):
        """Вывести список всех предметов"""
        print("\n" + "=" * 50)
        print("📚 ПРЕДМЕТЫ СЕМЕСТРА")
        print("=" * 50)
        for s in self.all():
            notes_count = len(s.notes_files)
            words = len(s.get_full_knowledge().split()) if notes_count else 0
            print(f"  [{s.subject_id}] {s.name}")
            print(f"    Конспектов: {notes_count} | Слов в базе: {words}")
            print(f"    Расписание: {s.schedule}")
        print("=" * 50 + "\n")
