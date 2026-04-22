"""
subjects.py — реестр предметов с накоплением знаний.
"""

import os
import json
from dataclasses import dataclass, field, asdict

NOTES_DIR = "notes"
REGISTRY_FILE = "subjects.json"


@dataclass
class Subject:
    name: str
    subject_id: str
    webinar_url: str = ""
    event_ids: list = field(default_factory=list)
    quiz_urls: list = field(default_factory=list)
    assignment_urls: list = field(default_factory=list)
    schedule: list = field(default_factory=list)
    duration_minutes: int = 90
    notes_files: list = field(default_factory=list)

    def get_full_knowledge(self) -> str:
        """Читает все накопленные конспекты по предмету."""
        all_notes = []
        for filepath in self.notes_files:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    all_notes.append(content)
        return "\n\n---\n\n".join(all_notes) if all_notes else ""

    def add_notes_file(self, filepath: str):
        if filepath not in self.notes_files:
            self.notes_files.append(filepath)


class SubjectRegistry:
    def __init__(self):
        os.makedirs(NOTES_DIR, exist_ok=True)
        self.subjects: dict = {}
        self._load()

    def add(self, subject: Subject):
        self.subjects[subject.subject_id] = subject
        self._save()
        print(f"✅ Добавлен предмет: {subject.name}")

    def get(self, subject_id: str) -> Subject:
        return self.subjects.get(subject_id)

    def all(self) -> list:
        return list(self.subjects.values())

    def add_notes(self, subject_id: str, notes_file: str):
        subject = self.get(subject_id)
        if subject:
            subject.add_notes_file(notes_file)
            self._save()

    def remove(self, subject_id: str) -> bool:
        if subject_id in self.subjects:
            del self.subjects[subject_id]
            self._save()
            return True
        return False

    def _save(self):
        data = {sid: asdict(s) for sid, s in self.subjects.items()}
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not os.path.exists(REGISTRY_FILE):
            return
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sid, sdata in data.items():
                self.subjects[sid] = Subject(**sdata)
            print(f"📖 Загружено предметов: {len(self.subjects)}")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки реестра: {e}")
