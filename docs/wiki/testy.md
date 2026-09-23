# Тесты и проверки

Тестам не нужна модель: ответы модели в них подставные. Часть тестов `designer` разбирает настоящие шаблоны из `docs/requirements/template/`; без этих файлов такие тесты пропускаются, а не падают.

## Сервис designer

1. Создайте окружение и поставьте пакет с тестовыми зависимостями:

   ```powershell
   python -m venv .venv-designer
   .venv-designer\Scripts\pip install -e "designer[dev]"
   ```

2. Запустите тесты из каталога `designer`:

   ```powershell
   cd designer
   ..\.venv-designer\Scripts\python -m pytest
   ```

Полный набор идёт около двух с половиной минут: 458 тестов на 23 сентября 2026 года.

## Интерфейс

1. Поставьте зависимости и запустите тесты:

   ```powershell
   cd frontend
   npm ci
   npm test
   ```

2. Соберите интерфейс, заодно пройдёт проверка типов:

   ```powershell
   npm run build
   ```

## Java-сервис речи

Java-тесты идут внутри сборки образа: `docker compose build app` падает, если тест красный.

## Сквозные прогоны на поднятом стеке

| Что проверяет | Команда | Режим в `.env` |
|---|---|---|
| живой режим от звука до слайда | `node scripts/live-smoke.mjs <запись.wav>` | `MODE=live` |
| текстовый ввод, фрагменты, повтор после обрыва | `node scripts/smoke.mjs` | `MODE=demo` |
| колода по брифу на всех шаблонах | `python examples/build.py examples/brief.txt` | любой |

Запись речи для первой строки делает `pwsh scripts/speech-sample.ps1`, подробнее на странице [живой режим](zhivoy-rezhim.md#из-записи-без-браузера).
