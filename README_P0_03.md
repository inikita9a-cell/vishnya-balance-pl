# P0-03 — исполнение выбранных Python-процедур

## Установка из корня репозитория

Распаковать ZIP поверх репозитория. В ZIP нет замены файлов `backend/`:
для `backend/runs.py` и `backend/api/procedures.py` приложен точечный патч. Остановить API, затем выполнить:

```powershell
git apply --ignore-space-change --check P0_03_backend.patch
git apply --ignore-space-change P0_03_backend.patch
python -m pytest tests/test_procedure_runtime.py -q
python tools/p0_03_smoke.py
python -m pytest tests -q
```

Если `--check` завершился ошибкой, патч не применять принудительно:
прислать вывод и текущие `backend/runs.py` и `backend/api/procedures.py`. Патч основан на ZIP из проекта.
После успешной установки перезапустить API и создавать НОВЫЙ запуск.
Новых зависимостей и миграций БД нет. Старые конфиги работают как прежде.

Ожидается: 24 новых теста проходят; smoke печатает `P0-03 OK`.
У автора: 131 тест всей папки `tests` прошли; проверены SQLite, Parquet,
выданные проверки и ноутбук. Полного датасета 2002 пар в исходном ZIP нет,
поэтому его повторный прогон нужно выполнить у себя.

## Как выбирать код (контракт для Backend 2 / Frontend)

`POST /api/procedures` сохраняет код, как раньше. Его числовой `id` прописать
в YAML конфига. `POST /api/runs` по-прежнему получает только `config_id`.
Backend 2 может сразу использовать эту схему в P0-02; менять REST не нужно.

```yaml
# Добавить к своему конфигу, ID заменить на реальные:
procedures:
  normalize: {procedure_id: 12, entry: normalize, params: {}, timeout_seconds: 120}
  compare: {procedure_id: 13, entry: compare, params: {}, timeout_seconds: 120}
  facts: {procedure_id: 14, entry: facts, params: {}, timeout_seconds: 120}
checks:
  - ar_drop_by_product
  - attribute_new_loss
  - external_score_drift
  - stop_factor_disappeared
  - target_model_changed
  - {id: my_check, procedure_id: 15, entry: check, params: {}}
```

Вместо `procedure_id` разрешены `{source: workspace, code: "...", params: {}}`
или `{source: file, path: procedures/my_code.py, params: {}}`.
При ID код и source берутся из Procedure текущего пользователя, а не из тела
запроса. Тип Procedure должен соответствовать этапу: normalize/compare/facts/check.
Пропущенный этап выполняется встроенным кодом. Пустой `procedures: {}` допустим.

| Вид | Функция | Результат |
|---|---|---|
| normalize | `normalize(before, after, cfg, params, app_id, issues)` | `(before_rows, after_rows)`: два списка нормализованных строк или DataFrame; затем движок применяет bucketize |
| compare | `compare(union_df, cfg, params, issues)` | DataFrame контракта comparison |
| facts | `facts(comparison, segments, cfg, params)` | `(facts_df, fact_apps_df)` |
| check | `check(mart, params)` либо официальный `CHECK` | `list[dict]` строк общего отчёта |

Рабочие примеры: `examples/p0_03/*.py`. Они предназначены для синтетического
smoke-теста; не подключать их автоматически к боевому конфигу.
`params` поступает выбранной процедуре; для checks `check_params[id]` имеет
приоритет над `params` процедуры. Для проверки на 1–3 заявках использовать
отдельный конфиг с `pool: {mode: list, app_ids: ["ID1", "ID2", "ID3"]}`.

## Что фиксируется и проверяется

- При постановке в очередь: исходник workspace/file, SHA-256 и параметры
  записываются в `Run.config_snapshot`; последующие изменения Procedure,
  исходного .py или конфига не меняют этот запуск и его повтор проверок.
- В `StageLog`: выбранный исходник и метаданные процедуры. Существующий
  `GET /api/runs/{rid}/steps/{step}` и экран этапа уже получают эти поля.
- В каталоге запуска: `procedures_snapshot.json` для CLI-проверки.
- Нормализация: обязательные колонки, APP_ID/SOURCE, типы, уникальность ключей.
  Сравнение: схема, ключи из входа, CHANGE_TYPE и согласованный DIFF_FLAG.
  Facts: схема, членство заявок и точное совпадение CNT с distinct APP_ID.
- Ошибка Python/контракта останавливает соответствующий этап; платформа
  пишет `failed`, исходник и диагностику. Ошибка отдельного check даёт ERROR-строку.
- Пользовательские этапы — отдельные процессы с таймаутом; нормализация
  всей выборки выполняется одним процессом, а не процессом на каждую заявку.
  Это исполнение доверенного кода, не изоляция файлов/сети.

## Граница этого пакета

Готовы движок, разрешение ID и журнал. Фронтенд не менялся: редактор Python
и выбор процедур в UI должен подключить фронтер. `POST /api/procedures/{pid}/try` поддерживает пробный прогон:
`{"config_id": 1, "app_ids": ["ID1"], "code": "черновик Python", "params": {}}`.
`code`, `params`, `entry` необязательны; без APP_ID выбираются первые три заявки.
Ответ: `{ok, result: {kind, app_ids, rows, columns, summary, events}}`; ошибка
контракта — `{ok: false, result: {error}}`. Черновик и Config не изменяются.
Запрос без `config_id` сохраняет старое поведение `/try`.
Полностью закрывать UI-часть P0-03 до подключения редактора нельзя.
