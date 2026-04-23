# Architecture

## Слои системы

```
Telegram (пользователь)
        │
        ▼
telegram_bot.py          ← единственная точка входа, ручной polling
        │
        ├── agent.py / SubjectAgent    ← оркестрация работы по предметам
        │       ├── browser.py / UniBrowser    ← Playwright, campus/online.fa.ru
        │       ├── smart_solver.py            ← решение тестов через Groq
        │       ├── essay_solver.py            ← написание заданий через Groq
        │       ├── quiz_digest.py             ← дайджест после теста
        │       ├── lecture_listener.py        ← МТС Линк API, запись лекций
        │       └── presence.py / PresenceKeeper ← удержание присутствия на вебинаре
        │
        ├── reactor_core/mirror.py / KnowledgeMirror  ← трекинг знаний, микро-квизы
        │       └── knowledge.db (SQLite)
        │
        └── subjects.py                ← реестр предметов, JSON-персистентность
                ├── subjects.json
                ├── teachers.json
                └── stats.json
```

## Ключевые модули

### telegram_bot.py
Ручной long-polling Telegram Bot API без сторонних фреймворков. Обрабатывает команды, callback-кнопки, пересланные расписания и прямые URL. Все тяжёлые операции — в daemon-потоках.

### agent.py / SubjectAgent
Оркестрирует полный цикл работы по предмету: лекция → тест → задание. Знает какой браузер использовать (`_make_browser()` читает `subject.source_platform`).

### browser.py / UniBrowser
Обёртка над Playwright Chromium. Принимает `base_url` — поэтому один класс работает и на campus.fa.ru, и на online.fa.ru.

### smart_solver.py / SmartSolver
Решает тесты через Groq. Использует `qa_cache.py` — одинаковые вопросы не пересылаются в API.

### reactor_core/mirror.py / KnowledgeMirror
SQLite-база уверенности по темам. Генерирует микро-квизы на основе конспектов, оценивает ответы семантически. Формула уверенности — сглаживание Лапласа: `(correct+1)/(total+2)`.

### subjects.py / SubjectRegistry
JSON-персистентность. Хранит ссылки на тесты, задания, конспекты, статусы. Метод `get_full_knowledge()` собирает все конспекты предмета в один текст для AI-контекста.

## Потоки данных

```
Лекция МТС Линк
    → lecture_listener.py → notes/{id}_{ts}.txt
    → SubjectRegistry.add_notes()
    → SmartSolver.knowledge (контекст для следующего теста)
    → QuizDigest (дайджест после теста)
    → KnowledgeMirror.generate_micro_quiz() (/learn)
```

## Переменные окружения

| Переменная | Описание |
|---|---|
| `TELEGRAM_TOKEN` | Bot API token |
| `TELEGRAM_CHAT_ID` | Твой chat ID |
| `GROQ_API_KEY` | Groq API key |
| `UNI_LOGIN` / `UNI_PASSWORD` | Кредиты campus/online.fa.ru |
| `UNI_URL` | Base URL (default: https://campus.fa.ru) |
| `MTS_TOKEN` | МТС Линк API token (опционально) |
| `SEMESTER` | Текущий семестр: "1" или "2" (default: 2) |
