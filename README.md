# PersoRAG

Telegram-бот для общения с персонажами на базе **RAG** (ChromaDB) + **Любой OpenAI-совместимый провайдер**.

---

## Возможности

- **RAG** поверх ChromaDB с локальными эмбеддингами `sentence-transformers`.
- **Мульти-персонаж** — у каждого свой system-промпт, своя база знаний и отдельная
  коллекция в Chroma. Пользователь выбирает персонажа командой `/character`.
- **LLM** — работает с любым OpenAI-совместимым эндпоинтом (OpenAI, собственный
  LiteLLM-прокси, vLLM, Ollama и т.д.).
- **Async + стриминг** — ответ печатается по мере генерации (редактируется сообщение
  в Telegram). Можно выключить флагом `STREAM_REPLIES=false`.
- **Персистентная история** — SQLite (`data/history.sqlite`). Переживает рестарты,
  на юзера хранится последних `MAX_HISTORY` сообщений **per-character**.
- **Чанкер** — `RecursiveCharacterTextSplitter` из `langchain-text-splitters`.
- **Rate-limit** и лимит длины входящего сообщения.
- **Режим приватности** — обычный пользователь видит только реплики персонажа.
  Служебные команды (`/clear`, `/character`, `/debug`, `/whoami`) доступны
  только админам из `ADMIN_USERS` и показываются в меню TG только им.
- **Работа в группах** — бот молчит в чате, пока его не «позвали»:
  триггерным словом из `TRIGGER_WORD`, упоминанием `@username` или реплаем.
- **Фото-реакции** — на определённые фразы можно настроить отправку
  картинки (см. `photos.json`).
- **Docker / docker-compose** для запуска в один шаг.

---

## Структура проекта

```
rag-character/
├── bot.py                # Telegram-обёртка (команды, стриминг, rate-limit)
├── chat.py               # CLI для отладки без Telegram
├── rag.py                # Ядро: retrieval + async generation
├── ingest.py             # Индексация knowledge/*.txt в Chroma
├── characters.py         # Реестр персонажей (загрузка из characters/<id>/)
├── storage.py            # SQLite: история и выбранный персонаж
├── config.py             # Загрузка настроек из .env
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── characters/           # Мульти-персонаж
│   └── <character_id>/
│       ├── system_prompt.txt
│       └── knowledge/
│           └── *.txt
├── chroma_db/            # векторная база (создаётся автоматически)
└── data/                 # SQLite c историей (создаётся автоматически)
```

### Мульти-персонаж

Папка `characters/<id>/`:

```
characters/
  persona/
    system_prompt.txt
    knowledge/
      biography.txt
      personality.txt
    photos.json          # (опционально) фото-реакции
    photos/
      cat.jpg
      angry.png
  alice/
    system_prompt.txt
    knowledge/
      lore.txt
```

### Фото-реакции (`photos.json`)

Кладёте файл `characters/<id>/photos.json` рядом с `system_prompt.txt` и
картинки в `characters/<id>/photos/`. Формат:

```json
[
  {
    "triggers": ["покажи кота", "котик", "cat"],
    "file": "cat.jpg",
    "caption": "мой рыжий паршивец"
  },
  {
    "triggers": ["злой", "бесишь"],
    "file": "angry.png",
    "caption": ""
  }
]
```

Совпадение по подстроке (регистр не важен). При первом же совпадении
после обычного текстового ответа бот отдельно дошлёт фото. Если ни один
триггер не подходит — фото не отправляется.

Имя коллекции в Chroma: `character_<id>`.

---

## Запуск в Docker

```bash
cp .env.example .env  

# первая индексация (одноразово и после изменений в knowledge/):
docker compose run --rm bot python ingest.py
# или конкретного персонажа:
docker compose run --rm bot python ingest.py persona

# запуск бота:
docker compose up -d
docker compose logs -f bot
```

Персистентные тома:

| Путь на хосте    | Путь в контейнере          | Назначение                  |
|------------------|----------------------------|-----------------------------|
| `./characters/`  | `/app/characters` (ro)     | персонажи (промпты + знания)|
| `./chroma_db/`   | `/app/chroma_db`           | векторная база              |
| `./data/`        | `/app/data`                | SQLite с историей           |
| `hf_cache` (vol) | `/app/.cache/huggingface`  | кэш модели эмбеддингов      |

Остановить:

```bash
docker compose down
```

---

## Поведение бота

### Приватный диалог
- Обычный пользователь видит **только** реплики персонажа. Никаких
  списков команд, id пользователей, системных сообщений.
- `/start` отрабатывает как обычное «Привет» — персонаж здоровается
  и начинается разговор.
- Технические команды (`/clear`, `/character`, `/debug`, `/whoami`)
  работают **только** для user_id из `ADMIN_USERS`. Остальным они
  даже не показываются в меню Telegram.

### Групповой чат
Добавьте бота в группу и **выключите ему Group Privacy** через @BotFather
(`/setprivacy → Disable`), иначе он не увидит обычные сообщения.

В группе бот молчит, пока его явно не «позвали»:

- сообщение содержит `TRIGGER_WORD` из `.env` (регистр не важен), **или**
- бот упомянут через `@username`, **или**
- сообщение — реплай на его же реплику.

Триггерное слово и упоминание вырезаются из текста перед отправкой
в LLM, чтобы персонажу не приходило лишнее.

### Админ-команды

| Команда           | Что делает                                       |
|-------------------|--------------------------------------------------|
| `/clear`          | очистить историю диалога для текущего персонажа  |
| `/character`      | показать доступных персонажей                    |
| `/character <id>` | переключиться на персонажа (история сбрасывается)|
| `/debug <текст>`  | показать, какие RAG-чанки подтянутся             |
| `/whoami`         | показать свой `user_id`                          |

---

## Переменные окружения

Полный список — в [`.env.example`](.env.example).

Ключевые:

| Переменная            | По умолчанию            | Назначение                                                        |
|-----------------------|-------------------------|-------------------------------------------------------------------|
| `TELEGRAM_TOKEN`      | —                       | токен бота от @BotFather                                          |
| `ALLOWED_USERS`       | пусто                   | CSV user_id с доступом; пусто = все                               |
| `ADMIN_USERS`         | пусто                   | CSV user_id админов (им доступны /clear, /character, /debug и т.д.)|
| `TRIGGER_WORD`        | пусто                   | слово-триггер в групповых чатах                                   |
| `LLM_BASE_URL`        | —                       | адрес OpenAI-совместимого эндпоинта                               |
| `LLM_API_KEY`         | —                       | ключ                                                              |
| `MODEL`               | `openai/gpt-4o-mini`    | имя модели                                                        |
| `MAX_TOKENS`          | `1024`                  | максимум токенов в ответе                                         |
| `STREAM_REPLIES`      | `true`                  | стримить ответ в TG через edit_message                            |
| `CHARACTERS_DIR`      | `./characters`          | корень с персонажами                                              |
| `DEFAULT_CHARACTER`   | `default`               | id персонажа по умолчанию                                         |
| `EMBEDDING_MODEL`     | `all-MiniLM-L6-v2`      | модель эмбеддингов (sentence-transformers)                        |
| `TOP_K`               | `5`                     | сколько чанков подтягивать                                        |
| `RELEVANCE_THRESHOLD` | `0.8`                   | cosine distance: чанки с `dist > threshold` отбрасываются         |
| `CHUNK_SIZE`          | `500`                   | размер чанка в символах                                           |
| `CHUNK_OVERLAP`       | `100`                   | перекрытие чанков                                                 |
| `MAX_HISTORY`         | `20`                    | сколько последних сообщений держать (per user+character)          |
| `HISTORY_DB`          | `./data/history.sqlite` | путь к SQLite                                                     |
| `MIN_INTERVAL_SEC`    | `1.5`                   | минимум секунд между сообщениями одного юзера                     |
| `MAX_INPUT_CHARS`     | `2000`                  | максимум символов во входящем сообщении                           |

---

## Как это работает

```
TG msg
  → handle_message (проверки: allowed, длина, rate-limit)
  → CharacterChat.reply_stream / reply
      ├─ get_user_character(user_id)           # из SQLite
      ├─ retrieve_context(collection, query)   # Chroma top-K + threshold
      ├─ build_system_prompt                   # base + <character_knowledge>
      ├─ storage.get_history(user_id, char_id) # последние MAX_HISTORY
      ├─ llm.acompletion(..., stream=True)
      └─ storage.add_message(user + assistant)
  → edit_message (стриминг) или reply_text
```

---

## Как добавить нового персонажа

1. Создайте папку `characters/my_hero/`.
2. Положите туда `system_prompt.txt` — базовый промпт отыгрыша.
3. Создайте `characters/my_hero/knowledge/` и набросайте туда `.txt` файлы
   (имя файла = категория чанка).
4. Запустите индексацию:

   ```bash
   python ingest.py my_hero
   # или в docker:
   docker compose run --rm bot python ingest.py my_hero
   ```
5. Перезапустите бота (`docker compose restart bot`).
6. В телеграме: `/character my_hero`.

---

## Известные ограничения

- Бот работает только с **текстом**. Голос, фото, стикеры, инлайн — пока не реализованы.
- Rate-limit простой и in-memory: при нескольких инстансах бота не синхронизируется.
- Кэш модели эмбеддингов грузится при первом запуске (~80 МБ для `all-MiniLM-L6-v2`).
- `llm.acompletion` со стримом совместим не со всеми провайдерами — при проблемах
  поставьте `STREAM_REPLIES=false`.
