# Этап 6: MartAPI и проверки — расположение `procedures/checks/`

В этом архиве **нет изменений платформенных файлов** `engine/mart.py`,
`engine/checks_runner.py`, `engine/sandbox.py`, `engine/llm.py`.
Он переносит пять оригинальных проверок заказчика в уже существующую папку
`procedures/checks/` и меняет только три пути по умолчанию в новых файлах этапа 6.

## Что копировать

Распакуйте архив **в корень репозитория**. Добавляются:

- `procedures/checks/check_*.py` — пять проверок из пакета задания, логика без изменений.
- `engine/mart_api.py` — рабочий MartAPI с фильтрами и `segments()`.
- `engine/checks_service.py` — загрузка проверок, исполнение, PASS/FAIL/ERROR.
- `engine/platform_checks_adapter.py` — вызов из платформенного бэка без сериализации Mart в JSON.
- `engine/run_checks.py` — CLI поверх готовых parquet (без повторного чтения исходных JSON).
- `tests/test_mart_checks.py`, `tests/test_platform_checks_adapter.py` — 14 тестов.

Новая корневая папка `checks/` **не нужна**. Путь к файлам проверок:
`procedures/checks/check_<id>.py`. Ключ конфигурации `overrides["checks/<id>"]`
**не является файловым путём** и остаётся неизменным для совместимости.
Временная папка `checks` внутри subprocess тоже не часть репозитория.

## Проверки на Windows (из корня репозитория)

```bash
py -m pytest -q tests
py -m engine.run_checks --run runs/check_002
```

Если сохранены все 36 предыдущих тестов, ожидается 50 passed (36 + 14).
В результате второго вызова должны появиться `runs/check_002/checks.json`
и `runs/check_002/checks_log.json`. Бизнес-результат FAIL допустим,
а ERROR требует расследования. Полная проверка 2002 заявок проводится у вас,
этот ZIP проверен на 14 новых тестах.

## Подключение к Backend 2 (после согласования с коллегой)

Сейчас её `engine/checks_runner.py` не умеет передавать объект Mart в subprocess:
он сериализуется в строку, плюс там есть фиктивный PASS. Эту проблему
**не исправить одним изменением пути**.

Чтобы сохранить существующий платформенный контракт, в её
`engine/checks_runner.py` достаточно делегировать вызов:

```python
def run_checks(state) -> str:
    from .platform_checks_adapter import run_checks as run_real_checks
    return run_real_checks(state)
```

Сигнатура и возвращаемое значение (путь к `checks.json`) не меняются.
Само изменение **не включено в архив**: его надо согласовать с Backend 2.
Её REST-маршруты, БД, журнал, `sandbox.py` и `llm.py` не трогаем.

## Границы и безопасность

- Адаптер умеет исполнять проверки из `procedures/checks/` и пользовательский
  код проверки из `cfg.checks`/`cfg.overrides`. В платформенной БД код может
  храниться иначе; маппинг согласовать с Backend 2.
- Subprocess с таймаутом защищает API от обычных ошибок и зависаний, но не
  является безопасной песочницей для недоверенного Python-кода.
- Одно место для будущей чистки дублирования: после интеграции решить,
  оставлять ли старый `engine/mart.py` как фасад или использовать
  `engine/mart_api.py` напрямую. Пока ничего не удалять.

## Conventional Commit (только после тестов)

```bash
git add engine/mart_api.py engine/checks_service.py engine/run_checks.py engine/platform_checks_adapter.py procedures/checks/check_*.py tests/test_mart_checks.py tests/test_platform_checks_adapter.py STEP6_INTEGRATION_README.md
git diff --cached --stat
git commit -m "feat(engine): add MartAPI and configurable business checks"
git push origin main
```

Не коммитить временные файлы в `runs/` и не добавлять `engine/` целиком.
