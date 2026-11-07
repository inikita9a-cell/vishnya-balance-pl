# Этап 7 — итоговая сводка, единый запуск, интеграция Backend 1 + Backend 2

Сборка подготовлена на основе `vishnya-balance-pl(1).zip` (актуальный архив пользователя от 7 ноября 2026 г.). Изменения **не затрагивают** `engine/checks_runner.py`, `engine/mart.py`, `engine/sandbox.py`, `engine/platform_checks_adapter.py`, API авторизации и SQLAlchemy-модели.

## Что поменялось

| Файл | Изменение |
|---|---|
| `backend/runs.py` | Вместо отсутствующих `steps.s1_discover ... s15` вызывает **один реальный** `engine.pipeline.run_pipeline`, пишет в существующую таблицу `StageLog` начало/прогресс/конец/исходный код. Перезапуск проверок обновляет Checks, Summary и HTML. Сигнатуры `start_run`, `run_pipeline`, `rerun_checks` сохранены. |
| `engine/pipeline.py` | Новый оркестратор: `prepare_comparison` → `checks_runner.run_checks` → `prepare_summary` → `write_report_html`. Есть CLI для сквозного теста. |
| `engine/steps.py` | Необязательный аргумент `on_event` для событий о стадиях и прогрессе. Логика нормализации и сравнения не менялась. |
| `engine/aggregates.py` | Необязательный `on_event` для блоков и фактов. Логика `CNT` не менялась. |
| `engine/report_html.py` | Был пустым. Генерирует самостоятельный HTML с CSS внутри и ссылками из строк проверок к API конкретной заявки. |
| `backend/api/data_api.py` | Исправлен импорт `Query`, Summary теперь JSON-объект. Для `/raw` добавлен fallback к исходному датасету из snapshot конфигурации вместо копирования в `runs/<id>/raw`. |
| `requirements.txt` | Добавлен отсутствовавший `sqlalchemy` (в проекте уже используются его модели). |
| `tests/test_full_platform_pipeline.py` | Новые тесты оркестрации, журналирования, перезапуска, HTML, REST и маленького реального сравнения. |

**Важное:** `backend/runs.py` пришлось существенно изменить, потому что прежний цикл ссылался на несуществующие функции `s1...s15`. Это замена **оркестрации**, а не пользовательской бизнес-логики или FastAPI-моделей. Другая часть платформы остаётся нетронутой.

## Как установить

1. Сделай резервную копию проекта или убедись, что изменения закоммичены.
2. Распакуй ZIP **в корень `vishnya-balance-pl`**, согласись заменить только перечисленные выше файлы. В ZIP **нет** `.git`, датасета, `runs/` или чужих незапрошенных модулей.
3. В Git Bash:

```bash
py -m pip install -r requirements.txt
py -m pytest -q tests
```

При установленных зависимостях ожидается **81 passed** (71 прежний тест и 10 новых, включая один реальный Parquet smoke test). В моей среде проверено **9 passed, 1 skipped** в новых тестах; `pyarrow`, `duckdb`, `xmltodict` отсутствуют, поэтому полный тестовый набор здесь не удалось выполнить.

## Важнейшая проверка — единый запуск через CLI

Это впервые запускает **всю цепочку** (а не только этапы 1–11) из одной команды:

```bash
py -m engine.pipeline --dataset "D:/Destruction/Nuclear Hack/ХАКАТОН_СИСТЕМА_АНАЛИЗА_ИЗМЕНЕНИЙ/ПАКЕТ/ЗАДАНИЕ/data/RUN-20260827-0001" --out runs/check_004
```

Используй новую папку `runs/check_004`, чтобы не затронуть старые результаты. Команда должна закончиться `status: done` и напечатать `[done] s15_report`. В папке должны лежать `comparison.parquet`, `segments.parquet`, `blocks.parquet`, `facts.parquet`, `fact_apps.parquet`, `quality.parquet`, `checks.json`, `summary.json`, **`report.html`**.

В `summary.json` по прежнему датасету ожидаем знакомые вычисленные числа: `total_apps=2002`, `apps_with_diff=502`, `apps_decision_changed=385` (это проверка воспроизводимости, **не** значения, зашитые в код).

## Проверка через настоящий Backend 2 / FastAPI

Запуск сервера из корня проекта:

```bash
py -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Открыть `http://127.0.0.1:8000/docs` и сделать запросы по порядку:

1. `POST /api/login` с `{"name":"demo"}`.
2. `POST /api/configs` — создать конфигурацию, где в YAML `dataset.path` указывает на **существующий каталог на твоём Windows**; путь по умолчанию `data/RUN-20260827-0001` сработает только если данные действительно есть по этому относительному пути.
3. `POST /api/runs` с `{"config_id": <ID созданной конфигурации>}`. Запомни `run_id`.
4. `GET /api/runs/{run_id}` — статус `queued` → `running` → `done`, видны `steps` и прогресс.
5. `GET /api/runs/{run_id}/summary` — **JSON-объект**, а не строка.
6. `GET /api/runs/{run_id}/checks` — результаты настоящих 5 проверок.
7. `GET /api/runs/{run_id}/report.html` — готовый HTML-протокол.
8. `GET /api/runs/{run_id}/steps/s7_compare` — исходный код, параметры, длительность.
9. `POST /api/runs/{run_id}/checks/rerun` — после выполнения обновляются `checks.json`, `summary.json`, `report.html`; нормализация не запускается повторно.

Для ссылок в скачанном HTML выстави `APP_BASE_URL=http://127.0.0.1:8000` (или адрес публичного приложения). Без этой настройки используется `http://localhost:8000`.

## Что **не** решено в этом точечном интеграционном пакете

- У платформенной процедуры `backend/api/procedures.py` остаются проблемы с preview пользовательского Python-кода и передачей `Mart` через JSON. Это отдельная задача Backend 2.
- `backend/duck.py` по-прежнему строит pivot напрямую по `comparison`, а не по готовому `facts` / `fact_apps`. Требует отдельного согласования с Backend 2 и фронтом.
- `docker-compose.yml` в старом ZIP ссылается на Dockerfile, которых там нет. Для текущей проверки используй `uvicorn` и CLI; Docker надо доделать отдельно.
- Фоновый `threading.Thread` живёт в процессе API. При его аварийном завершении задача не возобновится сама. Для MVP перезагрузка страницы работает (SQL logs остаются в БД), но восстановление после рестарта процесса ещё не реализовано.
- Это выделение процесса для проверок, **не защищённая песочница** для враждебного пользовательского Python-кода.

## Коммит (Conventional Commits)

Только после успешных тестов и сквозного CLI-прогона:

```bash
git status --short
git add backend/runs.py backend/api/data_api.py engine/steps.py engine/aggregates.py engine/pipeline.py engine/report_html.py requirements.txt tests/test_full_platform_pipeline.py BACKEND1_STEP7_INTEGRATION.md
git diff --cached --stat
git commit -m "feat(integration): connect platform runs to data pipeline"
git push origin main
```

`runs/` и датасет не добавлять в Git.
