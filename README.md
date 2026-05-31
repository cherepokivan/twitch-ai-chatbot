# Twitch AI Chatbot

Самописный AI-чатбот для Twitch: подключается к аккаунту бота, заходит на канал
стримера, читает чат (эту функцию можно выключить), наблюдает стрим через видео и
аудио, а затем отвечает в чат от имени заданного персонажа на базе LLM.

## Что умеет

- Подключаться к Twitch IRC от имени отдельного аккаунта бота.
- Заходить на указанный канал/стримера (`TWITCH_CHANNEL`).
- Отвечать стримеру или на упоминание бота в чате.
- Опционально читать последние сообщения чата как контекст для LLM.
- Опционально видеть стрим: периодически делает кадр через `streamlink` + `ffmpeg`
  и просит vision-модель кратко описать происходящее.
- Опционально слышать стрим: записывает короткие аудиофрагменты через `ffmpeg` и
  транскрибирует их.
- Иметь свою роль/персонажа, например: имя `Света`, возраст `22`, характер и лор.
- Команда `!ai togglechat` для стримера/модератора включает или выключает чтение
  чата для AI-контекста во время работы.

## Архитектура

```text
Twitch chat  ──► TwitchAIBot ──► RollingMemory ──► LLMClient ──► Twitch chat
Twitch HLS   ──► StreamObserver ─► кадры/аудио ──► LLMClient ──► RollingMemory
```

- `TwitchAIBot` отвечает за Twitch IRC, команды и антиспам-паузы.
- `StreamObserver` получает HLS-ссылку стрима через Streamlink, извлекает кадры и
  звук через ffmpeg.
- `LLMClient` генерирует ответы, описывает кадры и транскрибирует аудио через
  OpenAI API.
- `Persona` хранит роль бота и собирает system prompt.
- `RollingMemory` хранит короткий контекст чата и наблюдений стрима.

## Быстрый старт

### 1. Установите системные зависимости

Нужен Python 3.11+ и `ffmpeg`.

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg python3.11 python3.11-venv
```

Windows 10/11 через PowerShell и `winget`:

```powershell
winget install Python.Python.3.11
winget install Gyan.FFmpeg
```

После установки закройте и заново откройте PowerShell, затем проверьте, что
команды доступны:

```powershell
python --version
ffmpeg -version
```

Если `winget` недоступен, установите Python 3.11+ с https://python.org и ffmpeg с
https://ffmpeg.org, затем добавьте их в `PATH`.

### 2. Создайте Twitch bot account и OAuth token

Рекомендуется использовать отдельный Twitch-аккаунт для бота. Токену нужны scope:

- `chat:read`
- `chat:edit`

В `.env` токен можно указать как `oauth:...` или без префикса — приложение само
добавит `oauth:`.

### 3. Установите Python-зависимости

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Если PowerShell блокирует активацию виртуального окружения, разрешите выполнение
скриптов для текущего пользователя и повторите активацию:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1
```

### 4. Настройте `.env`

Linux/macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Минимальные обязательные переменные для Groq:

```dotenv
TWITCH_OAUTH_TOKEN=oauth:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWITCH_BOT_NICK=your_bot_login
TWITCH_CHANNEL=streamer_login
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_CHAT_MODEL=qwen/qwen3-32b
GROQ_TRANSCRIPTION_MODEL=whisper-large-v3-turbo
VOSK_ENABLED=off
OBSERVE_VIDEO=true
OBSERVE_AUDIO=true
FRAME_INTERVAL_SECONDS=5
AUDIO_INTERVAL_SECONDS=5
```

Минимальные обязательные переменные для OpenAI:

```dotenv
TWITCH_OAUTH_TOKEN=oauth:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWITCH_BOT_NICK=your_bot_login
TWITCH_CHANNEL=streamer_login
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Персонаж настраивается здесь же:

```dotenv
BOT_PERSONA_NAME=Света
BOT_PERSONA_AGE=22
BOT_PERSONA_ROLE=дружелюбная, немного ироничная AI-подруга стримера; отвечает коротко, живым разговорным русским языком
BOT_PERSONA_EXTRA=любит шутить про игровые мисплеи, но не оскорбляет зрителей
```

### 5. Запустите

Linux/macOS или активированное Windows-окружение:

```bash
twitch-ai-chatbot
```

Windows PowerShell без entrypoint можно запустить так:

```powershell
python -m twitch_ai_chatbot.main
```

Или без чтения чата:

```bash
twitch-ai-chatbot --no-chat-context
```

Или без наблюдения стрима, только чат:

```bash
twitch-ai-chatbot --no-stream
```


## Настройка Groq вместо OpenAI

Groq поддерживается через OpenAI-compatible API: приложение использует тот же
`openai` Python SDK, но с `GROQ_API_KEY` и `GROQ_BASE_URL=https://api.groq.com/openai/v1`.

Пример `.env` для Groq и модели из вашего списка:

```dotenv
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_CHAT_MODEL=qwen/qwen3-32b
GROQ_TRANSCRIPTION_MODEL=whisper-large-v3-turbo
VOSK_ENABLED=off
```

Можно поставить другую текстовую модель Groq, например:

```dotenv
GROQ_CHAT_MODEL=qwen/qwen3-32b
# или
GROQ_CHAT_MODEL=llama-3.3-70b-versatile
# или
GROQ_CHAT_MODEL=groq/compound-mini
```

По умолчанию для Groq используются **три разные модели параллельно по задачам**:

- `GROQ_VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct` — смотрит кадры
  стрима и пишет короткое описание происходящего.
- `GROQ_TRANSCRIPTION_MODEL=whisper-large-v3-turbo` — слушает аудио стрима и
  превращает речь в текст.
- `GROQ_CHAT_MODEL=qwen/qwen3-32b` — думает на основе чата, описаний видео и
  транскрипта аудио, затем отвечает в Twitch-чат от лица персонажа.

```dotenv
OBSERVE_VIDEO=true
OBSERVE_AUDIO=true
GROQ_VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
GROQ_TRANSCRIPTION_MODEL=whisper-large-v3-turbo
GROQ_CHAT_MODEL=qwen/qwen3-32b
```

Можно заменить `GROQ_CHAT_MODEL` на другую текстовую модель из Groq. Если поставить
текстовую модель в `GROQ_VISION_MODEL`, кадры стрима описываться не будут — для
картинки нужна именно vision-модель.

## Более частое видео и почти real-time аудио

По умолчанию в `.env.example` наблюдение сделано чаще, чем было в первом варианте:

```dotenv
FRAME_INTERVAL_SECONDS=5
AUDIO_INTERVAL_SECONDS=5
```

Это означает, что бот примерно раз в 5 секунд берет кадр стрима, а аудио режет на
короткие 5-секундные фрагменты. Можно поставить `1-2` секунды, но это резко
увеличит нагрузку на CPU, `ffmpeg`, сеть и лимиты провайдера. Для Groq/Whisper
обычно разумный минимум — 2-5 секунд.

Если нужно распознавать речь **без облачного AI/STT API**, можно включить локальный
Vosk:

```dotenv
VOSK_ENABLED=on
VOSK_MODEL_PATH=models/vosk-model-small-ru-0.22
AUDIO_INTERVAL_SECONDS=2
```

Для Vosk нужно заранее скачать русскую модель с сайта Vosk, распаковать ее в папку
`models/` и указать путь в `VOSK_MODEL_PATH`. Качество Vosk обычно хуже, чем у
`whisper-large-v3-turbo`, особенно на шумном стриме, зато распознавание идет
локально и не тратит API-токены. Временные `.wav` файлы все равно удаляются после
каждого фрагмента.


## Идея для будущего интерфейса

Следующий удобный шаг — добавить локальную панель управления, например
`http://localhost:7860`, чтобы не редактировать `.env` руками. Возможный план:

1. Добавить web-сервер на FastAPI/Flask с простым HTML-интерфейсом.
2. На странице показать те же поля, что есть в `.env`: Twitch token/nick/channel,
   Groq/OpenAI модели, persona, `READ_CHAT`, `OBSERVE_VIDEO`, `OBSERVE_AUDIO`,
   `FRAME_INTERVAL_SECONDS`, `AUDIO_INTERVAL_SECONDS`, `VOSK_ENABLED` и т.д.
3. Кнопка `Save` будет перезаписывать `.env`, а кнопка `Restart bot` — мягко
   перезапускать процессы наблюдения и Twitch-бота.
4. Добавить страницу статуса: подключен ли Twitch, идет ли стрим, последнее
   описание кадра, последний распознанный аудиотекст, последние ошибки ffmpeg/Groq.
5. Для безопасности слушать только `127.0.0.1` и не открывать панель наружу в интернет,
   потому что там будут токены.

Так получится отдельная локальная программа/панель, где все настройки будут как в
`.env`, но с нормальными переключателями `on/off`, полями ввода и кнопками.

## Получение Twitch OAuth token на Windows

1. Зарегистрируйте приложение в Twitch Developer Console с категорией `Chat Bot`.
2. В `OAuth Redirect URL` добавьте тот redirect, который использует Twitch CLI.
   Обычно достаточно добавить оба варианта:

   ```text
   http://localhost
   http://localhost:3000
   ```

   Ошибка `redirect_mismatch` означает, что redirect из запроса не совпадает с
   redirect URL, зарегистрированным в приложении.
3. Скачайте Twitch CLI для Windows, распакуйте архив и откройте PowerShell в папке
   с `twitch.exe`.
4. Настройте CLI через `Client ID` и `Client Secret` вашего приложения:

   ```powershell
   .\twitch.exe configure
   ```

5. Получите user token для аккаунта бота:

   ```powershell
   .\twitch.exe token -u -s 'chat:read chat:edit'
   ```

6. В открывшемся браузере войдите именно в Twitch-аккаунт бота и разрешите доступ.
   Полученный токен вставьте в `.env` как `TWITCH_OAUTH_TOKEN`.

## Важные настройки

| Переменная | Значение по умолчанию | Описание |
| --- | --- | --- |
| `LLM_PROVIDER` | `groq` | Провайдер LLM: `groq` или `openai`. |
| `GROQ_CHAT_MODEL` | `qwen/qwen3-32b` | Основная Groq-модель, которая думает и отвечает в чат. |
| `GROQ_TRANSCRIPTION_MODEL` | `whisper-large-v3-turbo` | Groq-модель для распознавания аудио стрима, если `VOSK_ENABLED=off`. |
| `VOSK_ENABLED` | `off` | `off` использует Groq/OpenAI Whisper; `on` распознает речь локально через Vosk. |
| `VOSK_MODEL_PATH` | `models/vosk-model-small-ru-0.22` | Путь к локальной модели Vosk, если выбран `VOSK_ENABLED=on`. |
| `READ_CHAT` | `true` | Можно ли отправлять последние сообщения чата в LLM-контекст. |
| `OBSERVE_STREAM` | `true` | Включает наблюдение стрима. |
| `OBSERVE_VIDEO` | `true` | Включает описание кадров через отдельную vision-модель Groq. |
| `OBSERVE_AUDIO` | `true` | Включает транскрибацию аудио. |
| `TRIGGER_MODE` | `mention` | `mention`, `streamer` или `all`. |
| `MIN_SECONDS_BETWEEN_REPLIES` | `20` | Минимальная пауза между ответами бота. |
| `REPLY_PROBABILITY` | `1.0` | Вероятность ответа после срабатывания триггера. |
| `MAX_REPLY_CHARS` | `420` | Ограничение длины ответа для Twitch-чата. |
| `FRAME_INTERVAL_SECONDS` | `5` в `.env.example` | Как часто анализировать кадр стрима; можно снизить до 1-2 секунд ценой нагрузки. |
| `AUDIO_INTERVAL_SECONDS` | `5` в `.env.example` | Длина аудиофрагмента для транскрибации; меньше значение = ближе к real-time. |

## Команды в чате

По умолчанию prefix — `!ai`.

- `!ai persona` — показать имя/возраст/роль бота.
- `!ai togglechat` — включить/выключить чтение чата для LLM-контекста. Команда
  работает только для стримера или модератора.

## Как бот решает, когда отвечать

`TRIGGER_MODE=mention`:

- отвечает, если стример пишет в чат;
- отвечает, если в сообщении упомянут логин бота;
- не отвечает чаще, чем разрешает `MIN_SECONDS_BETWEEN_REPLIES`.

`TRIGGER_MODE=streamer`:

- отвечает только на сообщения стримера.

`TRIGGER_MODE=all`:

- может отвечать на любое сообщение, поэтому лучше увеличить паузу и/или снизить
  `REPLY_PROBABILITY`, чтобы не спамить.

## Ограничения и безопасность

- Бот видит стрим по открытой HLS-трансляции Twitch; если канал офлайн или Twitch
  ограничил доступ, наблюдений не будет.
- Видео/аудио наблюдение потребляет токены LLM и CPU, поэтому интервалы лучше не
  делать слишком маленькими.
- Не запускайте бота с OAuth-токеном вашего основного аккаунта стримера.
- Не выдавайте боту права модератора, пока не протестировали persona prompt,
  антиспам-настройки и команды.
