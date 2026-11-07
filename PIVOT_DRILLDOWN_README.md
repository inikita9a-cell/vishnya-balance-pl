# Fix: Pivot / Drill-down — точный COUNT(DISTINCT APP_ID)

**Изменяем только `backend/duck.py` и добавляем `tests/test_duck_pivot.py`.** Остальные файлы платформенного бэка, конфигурации, HTML, `requirements.txt` и API не трогаем.

## Зачем

Предыдущий `pivot()` использовал `SUM(CNT)` из `facts.parquet`. Это неверно при произвольном группировании: `CNT` посчитан по *полной* комбинации измерений, а один APP_ID встречается в нескольких `PATH`, `SOURCE` и т.д. Также старый `drilldown()` использовал несогласованные фильтры и имел неточный fallback к `comparison.parquet`.

Теперь `pivot()` и `drilldown()` фильтруют **один и тот же** набор записей `facts INNER JOIN fact_apps ON FACT_ID`, а `pivot()` считает `COUNT(DISTINCT fa.APP_ID)`. `drilldown()` получает `SELECT DISTINCT fa.APP_ID` и добавляет данные из `segments`.

## Применение в твоей репе

1. Сначала **`git pull origin main`**, если Бэк 2 уже запушила новые изменения.
2. Распакуй ZIP во временную папку. Рекомендуемый безопасный способ — сначала проверить патч:

   ```bash
   git apply --check pivot_distinct.patch
   git apply pivot_distinct.patch
   ```

   Если проверка не прошла, **не применяй** патч вслепую: значит, `backend/duck.py` уже изменён. Сверь отличия вручную (или пришли файл сюда).
3. Скопируй `tests/test_duck_pivot.py` в `tests/` твоего проекта.
4. Из корня репозитория проверь:

   ```bash
   py -m pytest -q tests/test_duck_pivot.py
   py -m pytest -q tests
   ```

   При установленных DuckDB и PyArrow прогонится и тест на **настоящем** Parquet. У разработчика было 12 пройденных тестов + 1 пропуск, так как в среде разработки нет DuckDB/PyArrow. У тебя ожидаем без пропусков.

## Проверить на реальном `runs/check_003` (или новом `run_id`)

В Git Bash, из корня проекта:

```bash
py -c "from pathlib import Path; from backend.duck import pivot, drilldown; p=Path('runs/check_003'); x=pivot(p, ['CHANGE_TYPE'], ['SOURCE'], {}); print(x); assert all(len(drilldown(p, {'CHANGE_TYPE':r['CHANGE_TYPE'],'SOURCE':r['SOURCE']}))==r['CNT'] for r in x['rows']); print('PIVOT/DRILLDOWN MATCH')"
```

Это сравнит **каждую** возвращённую ячейку с реальным числом уникальных заявок в её провале. Важно: `runs/check_003` должен содержать `facts.parquet`, `fact_apps.parquet`, `segments.parquet`. Запускать расчёт JSON повторно не надо.

## Контракт для фронта (без изменений API)

- `POST /api/runs/{rid}/pivot`: `{ "rows": ["CHANGE_TYPE"], "cols": ["SOURCE"], "filters": {} }`.
- Ответ как раньше: `{"columns": ..., "rows": [{"CHANGE_TYPE":"...","SOURCE":"...","CNT": N}], "dims": ["CHANGE_TYPE","SOURCE"]}`.
- **При клике по ячейке:** собери `filters` из глобальных фильтров текущей сводной **ПЛЮС значения всех строковых/колоночных измерений ячейки**. Пример: `{ "filters": { "CHANGE_TYPE": "VALUE_CHANGED", "SOURCE": "AFTER (BETA)" } }` на `POST /api/runs/{rid}/drilldown`.
- `len(drilldown response) == CNT` для этой ячейки. Для выбранных значений NULL передавай JSON `null`.
- **Не суммируй `CNT` по другим строкам для grand total:** на пересекающихся группах будут дубли. Точный общий итог получается `len(drilldown(run, global_filters))` (или отдельным запросом `COUNT(DISTINCT APP_ID)`).

## Важно

- Для точного провала `fact_apps.parquet` обязателен; неточная подмена на `comparison` удалена.
- Некорректное имя измерения или фильтра теперь приводит к `ValueError`, а не молча игнорируется. Сейчас внешний API не переводит её в `422`, поэтому не отправляй произвольные названия: используй измерения из `facts`.
- Новые конфигурируемые колонки `facts` (например, `ARRAY_KEY`) доступны автоматически, без жёстко заданного списка.
- Пока не исправлена обработка ошибок в FastAPI-эндпоинтах, неверный фильтр может дать HTTP 500 вместо 400; это отдельная необязательная правка платформы.

**Conventional Commit (только после проверки):**

```bash
git add backend/duck.py tests/test_duck_pivot.py
git commit -m "fix(pivot): count distinct applications in pivot and drilldown"
git push origin main
```
