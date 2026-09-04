# Subscription Analyzer Telegram MVP

Первый запускаемый MVP: Telegram-бот принимает PDF-выписку, извлекает операции, отдельно классифицирует регулярные платежи и формирует отчёт по вероятным подпискам.

## Пользовательский сценарий

1. Пользователь нажимает `/start`.
2. Бот показывает кнопку **«📄 Получить выписку»**.
3. Бот переводит пользователя в режим ожидания и показывает кнопку **«🏦 Открыть СберБанк Онлайн»**.
4. Кнопка ведёт на наш HTTPS redirect endpoint `/sber`.
5. Redirect определяет Android/iOS по User-Agent и пытается открыть настроенный deeplink Сбера; при невозможности используется веб-версия СберБанк Онлайн.
6. Пользователь вручную получает выписку в официальном интерфейсе Сбербанка.
7. Пользователь возвращается в Telegram и отправляет PDF.
8. Бот обрабатывает PDF во временном файле, извлекает текст и удаляет файл после обработки.
9. Сначала применяется слой классификации: **операция → регулярный платёж → определить тип**.
10. Только подходящие сервисные операции попадают в детектор подписок.
11. Бот отправляет отчёт с найденными кандидатами, суммой, периодичностью, количеством повторений, confidence и объяснением.

## Device-aware redirect

Telegram Bot API для inline-кнопки принимает HTTP или `tg://` URL, поэтому бот использует HTTPS URL нашего redirect-сервера, а не пытается напрямую передать custom scheme приложения Сбера.

Для production в `.env` нужно указать публичный HTTPS адрес сервера:

```text
PUBLIC_BASE_URL=https://bot.example.com
WEB_PORT=8080
SBER_ANDROID_DEEPLINK=sberbankonline://sberbankid/sso
SBER_IOS_DEEPLINK=sberbankonline://sberbankid/sso
```

Сервер поднимает:

- `GET /sber` — определение платформы и best-effort запуск приложения Сбера;
- `GET /health` — health check.

Важно: официальная документация Сбера описывает такие deeplink'и в контексте Sber ID/SSO и предупреждает, что схема Sber ID может меняться. Поэтому MVP не обещает открытие конкретного экрана личной выписки и хранит deeplink'и в конфигурации.

При отсутствии `PUBLIC_BASE_URL` бот безопасно возвращается к прямой HTTPS-ссылке `SBER_ONLINE_URL`. Для реального device-aware сценария сервер должен быть доступен пользователю по публичному HTTPS адресу.

## Ограничения MVP

- Прямой retail API Сбербанка для чтения операций физлица ранее не был подтверждён. Поэтому выписка передаётся в бот пользователем.
- Автоматический вход в Сбербанк, сбор логина/пароля/SMS-кодов, cookies или reverse engineering не используется.
- Сейчас поддерживается PDF с текстовым слоем. Сканированные PDF без текстового слоя потребуют OCR в отдельной задаче.
- В MVP нет автоматической отмены подписок.
- Данные выписки не сохраняются после обработки; файл удаляется из временного каталога.
- Для production понадобится постоянное хранилище состояния, очередь задач, ограничения доступа, аудит и отдельная security/legal проверка.

## Запуск

Нужен Python 3.13+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

В `.env` укажи токен Telegram-бота и публичный HTTPS адрес redirect-сервера:

```text
BOT_TOKEN=...
SBER_ONLINE_URL=https://online.sberbank.ru/
PUBLIC_BASE_URL=https://bot.example.com
WEB_PORT=8080
SBER_ANDROID_DEEPLINK=sberbankonline://sberbankid/sso
SBER_IOS_DEEPLINK=sberbankonline://sberbankid/sso
MAX_FILE_SIZE_MB=15
```

Запуск:

```bash
python -m app.bot
```

Для локального запуска без публичного HTTPS адреса бот продолжит работать, но кнопка будет открывать `SBER_ONLINE_URL` напрямую. Для проверки device-aware redirect нужен публичный HTTPS reverse proxy/tunnel или сервер с доменом.

Docker:

```bash
docker build -t subscription-analyzer .
docker run --rm --env-file .env -p 8080:8080 subscription-analyzer
```

Тесты:

```bash
pytest -q
```

## Структура

- `app/bot.py` — Telegram UI, состояние ожидания файла, загрузка PDF, отчёт и запуск HTTP redirect-сервера.
- `app/sber_redirect.py` — определение Android/iOS, запуск deeplink Сбера и web fallback.
- `app/analyzer.py` — извлечение операций из текста, классификация, нормализация merchant и детектор подписок.
- `tests/test_analyzer.py` — regression-тесты классификации и подписок.
- `tests/test_sber_redirect.py` — тесты определения платформы и redirect HTML.
- `.env.example` — шаблон переменных, без секретов.
