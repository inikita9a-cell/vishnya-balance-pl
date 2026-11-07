# Бэк 1 — этап 5: массовые изменения (blocks) и facts для веб-сводной (s10–s11)

Архив накладывается **поверх успешного этапа 4**, который вы уже прогнали на Windows:
`29 passed`, `2002` заявки, `comparison.parquet` и `segments.parquet` в `runs/check_002`.

Новые файлы:
- `engine/aggregates.py` — чистые шаги `blocks` и `facts`, без имён полей исходного датасета;
- `engine/run_aggregates.py` — консольный запуск только s10–s11 для готового прогона;
- `tests/test_blocks_facts.py` — 7 тестов, включая уникальные заявки, разные виды изменений и повторное использование старого прогона.

Обновлены:
- `engine/steps.py` — экспортирует `blocks`, `facts`, `prepare_aggregates`; `prepare_comparison` автоматически вызывает s10–s11 после s9;
- `engine/run_comparison.py` — описание всей цепочки;
- `configs/default_spr.yaml` — параметры агрегатов.

**Не удаляйте старые `engine/paths.py`, `engine/adapters.py` и другие файлы проекта.** Архив содержит только изменения этапа 5. `runs/` с результатами **не коммитим**.

## Самый быстрый путь — построить агрегаты по уже готовому прогону

Из корня репозитория после распаковки и замены файлов:

```bash
py -m pytest -q tests
py -m engine.run_aggregates --run runs/check_002
```

Если `runs/check_002` находится по другому пути, укажите его в `--run`.
Это **не читает заново 4004 JSON**: только два уже рассчитанных Parquet-файла.

Ожидаемая структура `runs/check_002/` после успеха:

```
union.parquet
comparison.parquet
quality.parquet
segments.parquet
blocks.parquet       # новый
facts.parquet        # новый
fact_apps.parquet    # новый: точные связи групп с APP_ID
comparison_status.json   # stage: facts, дополнительные количества и время
```

Затем можно повторить полный путь с нуля (не используйте уже занятую папку):

```bash
py -m engine.run_comparison --dataset "D:/Destruction/Nuclear Hack/ХАКАТОН_СИСТЕМА_АНАЛИЗА_ИЗМЕНЕНИЙ/ПАКЕТ/ЗАДАНИЕ/data/RUN-20260827-0001" --out runs/check_003
```

## Что именно считается

### blocks.parquet

Таблица по уровням вложенности `BLOCK` / `LEVEL`. Например, для
`decisionResult.product_trials.rules.hit` создаются узлы:
`decisionResult`, `decisionResult.product_trials`,
`decisionResult.product_trials.rules`.
По умолчанию лист `hit` — не отдельный блок.

- `APPS_TOTAL`: число **уникальных APP_ID, имеющих наблюдаемые строки в блоке**;
- `APPS_CHANGED`: число уникальных APP_ID, где в блоке есть хоть одно изменение;
- `SHARE`: `APPS_CHANGED / APPS_TOTAL`, доля 0..1;
- `ROWS_TOTAL`, `ROWS_CHANGED`: количество атрибутных строк, НЕ число заявок;
- `APPS_VALUE_CHANGED`, `APPS_ATTRIBUTE_NEW`, `APPS_ATTRIBUTE_LOST`: уникальные заявки по типу изменения;
- `ROWS_VALUE_CHANGED`, `ROWS_ATTRIBUTE_NEW`, `ROWS_ATTRIBUTE_LOST`: строки по типу;
- `APPS_INCOMPLETE`: сколько заявок в данном блоке имеют `COMPARISON_COMPLETE=0`.

Показатели `APPS_*` разных типов **не складываются**: одна заявка может иметь несколько видов изменений. `APPS_TOTAL` — покрытие блока, а не обязательно все 2002 заявки; для корректного отображения показывайте числитель и знаменатель.

### facts.parquet

Вертикальная витрина с `SOURCE=BEFORE (MASTER)` или `AFTER (BETA)`, а не горизонтальными полями BEFORE/AFTER. В каждой записи есть `FACT_ID`, измерения (`PATH`, `KEY`, `VALUE_ADJUSTED`, `DIFF_FLAG`, `CHANGE_TYPE`, `SOURCE`, разрезы из `segments`) и мера `CNT = COUNT(DISTINCT APP_ID)`.

- `ATTRIBUTE_NEW` появляется **только в AFTER**, `ATTRIBUTE_LOST` — **только в BEFORE**.
- `SAME` и `VALUE_CHANGED` представлены в обоих срезах.
- Настоящее JSON `null` представлено строкой `"NULL"`; это **не** потерянный атрибут.
- По умолчанию `ARRAY_KEY` не входит в измерения агрегата: разные элементы массива одной заявки в одном бакете считаются один раз. Если нужен разрез по конкретным элементам, выставьте `facts.include_array_key: true` (увеличит объём).
- Какие поля из `segments` входят в группировку, настраивается через `facts.segment_dimensions`.

**Важно для фронта и бэка 2:** `CNT` неаддитивен при произвольной смене раскладки. Например, одна заявка может попасть в два разных бакета значения и в два разных пути. `SUM(CNT)` в таком случае даст не уникальные заявки. Для точного числа в новой раскладке делайте `COUNT(DISTINCT APP_ID)` по `fact_apps.parquet` после фильтрации facts, или считайте группировку заново по исходным строкам.

### fact_apps.parquet

Две колонки: `FACT_ID`, `APP_ID`; уникальная пара (группа, заявка).
Это связь для перехода от ячейки к списку заявок. Пример запроса в DuckDB:

```sql
SELECT DISTINCT m.APP_ID
FROM read_parquet('runs/check_002/facts.parquet') AS f
JOIN read_parquet('runs/check_002/fact_apps.parquet') AS m USING (FACT_ID)
WHERE f.PATH = 'decisionResult.decision'
  AND f.SOURCE = 'AFTER (BETA)'
  AND f.DIFF_FLAG = 1
ORDER BY m.APP_ID;
```

Для отдельного `FACT_ID` достаточно найти `APP_ID` в `fact_apps`. Для клика по суммарной ячейке сводной сначала выберите все соответствующие `FACT_ID`, потом `DISTINCT APP_ID` по их объединению.

## Интерфейсы для бэка 2

```python
from engine.steps import blocks, facts, prepare_aggregates

blocks_df = blocks(comparison_df, segments_df, cfg)
facts_df, fact_apps_df = facts(comparison_df, segments_df, cfg)
status = prepare_aggregates(run_dir, cfg)  # для уже готового s9
```

`from engine.steps import prepare_comparison` сохраняется. Для новых полных прогонов результат теперь включает s10 и s11.

## Проверки и ограничения

Новые 7 тестов выполнены на искусственных данных без имён из датасета. Выполнены также синтетические замеры на 289 533 строках; они **не являются** проверкой настоящего датасета или скорости на вашем Windows. Для полного подтверждения нужен ваш `py -m pytest -q tests` и расчёт `py -m engine.run_aggregates`.

Временный `pyarrow` не был доступен в среде сборки, поэтому тест чтения/записи parquet здесь сделан через подмену файлового кодека; реальный Parquet вы уже успешно читали и записывали на этапе 4. В этом ZIP новых зависимостей нет.

Следующий этап: `MartAPI` и пять выданных проверок (s12).

## Коммит: Conventional Commits

После успешного результата из корня репозитория:

```bash
git add engine/steps.py engine/aggregates.py engine/run_aggregates.py engine/run_comparison.py configs/default_spr.yaml tests/test_blocks_facts.py BACKEND1_STEP5.md
git diff --cached --stat
git commit -m "feat(engine): add block aggregates and pivot facts"
git push origin main
```
