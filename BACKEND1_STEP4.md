# Бэк 1 — качество данных и разрезы (s8–s9)

Применить поверх этапов 2 и 3. В архиве только:
- engine/steps.py — дополнены quality, segments, существующий prepare_comparison;
- engine/run_comparison.py — та же команда, понятная ошибка занятой папки;
- configs/default_spr.yaml — добавлена проверка причин по каждому продукту;
- tests/test_quality_segments.py — новые проверки;
- эта инструкция.

Если конфиг уже меняли вручную, сохраните свои настройки и добавьте только второе
правило quality.reason_rules с scope_path из версии в архиве. Остальные значения
дефолтного конфига те же, что на предыдущем этапе.

## Что выполнить (из корня репозитория)

```bash
py -m pytest -q tests
py -m engine.run_comparison --dataset "D:/Destruction/Nuclear Hack/ХАКАТОН_СИСТЕМА_АНАЛИЗА_ИЗМЕНЕНИЙ/ПАКЕТ/ЗАДАНИЕ/data/RUN-20260827-0001" --out runs/check_002
```

Ожидаемый итог тестов: 29 passed. Если check_002 уже занят, выберите check_003.
Предыдущий runs/check_001 остаётся доступным, но новых segments в нём не будет.

Новых зависимостей нет. Проверено на Python 3.12. Полного датасета в среде
разработки нет: выполнен дополнительный локальный прогон четырёх публичных пар
из samples, без использования expected_OPEN/HOLDOUT/FULL: 4 строки segments,
3 заявки с различиями, 2 смены решения, 0 проблем качества. Это результат расчёта
на этих четырёх парах, а не ожидаемые числа для полного датасета.

## Что появилось

segments.parquet — одна строка на каждый выбранный APP_ID, включая повреждённые
и отсутствующие пары. Остальные таблицы этапа 3 сохраняются.

В comparison_status.json добавлены:
- segment_rows — число строк разрезов;
- apps_with_diff — заявки с хотя бы одним наблюдаемым различием;
- apps_decision_changed — смены решения только там, где оба решения известны;
- apps_decision_comparable — число заявок, где оба решения известны;
- apps_with_quality_issues — заявки с проблемами;
- apps_comparison_incomplete — заявки с неполным/ненадёжным сравнением;
- cause_counts — распределение CAUSE;
- duration_seconds — время локального прогона с записью Parquet.

diff_rows остаётся количеством различий атрибутов; apps_with_diff — количеством
заявок. Это разные показатели. Файл технический, финальный summary.json будет
реализован на соответствующем этапе.

## Интерфейсы для бэка 2

```python
from engine.steps import quality, segments, prepare_comparison

# doc_pairs: list[{APP_ID: str, BEFORE: dict | None, AFTER: dict | None}]
quality_df = quality(doc_pairs, cfg, existing_issues)
segments_df = segments(doc_pairs, comparison_df, cfg, quality_df)
status = prepare_comparison(cfg, run_dir)  # прежняя сигнатура, теперь до s9
```

None означает отсутствующий или непрочитанный документ; {} — корректный пустой
объект. Ошибки чтения/отсутствия добавляет load и передаёт existing_issues.
Конфиг и исходные документы не изменяются.

## Правила качества

Проверки идут по исходным документам, а не по отфильтрованной витрине:
исключение поля из сравнения не делает его отсутствующим в исходном файле.

required_paths: отсутствующий путь, null, пустая или пробельная строка дают
REQUIRED_FIELD_MISSING. Число 0 и bool false — заполненные значения. Для пути
внутри массива проверяется каждый найденный родительский объект.

reason_rules: when_path/when_value/require_path. Если задан scope_path, условие
и требуемое поле проверяются внутри каждого выбранного объекта. Поэтому причина
у продукта A не покрывает отсутствие причины у отказанного продукта B. У
одобренного продукта null в причине допустим. Без scope_path достаточно одной
непустой причины во всём документе при сработавшем условии.

Также поддержан формат основного брифа:
when: "decision == 'REJECT'", require: reject_code — имена берутся из segments.
Поддержано только равенство имени константе; eval и произвольного исполнения нет.

Сохраняются ранее собранные PARSE_ERROR, APP_MISSING_*, DUPLICATE_KEY,
DEPTH_TRUNCATED, ARRAY_KEY_MISSING, ARRAY_KEY_FALLBACK.

## Правила разрезов

- Все пути, включая фильтр rank=1 для лучшего оффера, берутся из segments конфига.
- PRODUCTS, PARTNER_TYPE, ROUTING_METHOD — объединение обоих срезов, уникальные
  значения в отсортированном виде через ';'.
- REASON_BEFORE/AFTER — конкретные коды из reject_code;
  REJECT_REASON_BEFORE/AFTER — классы причин из reject_reason.
- Для одобрения отсутствие причины нормально; в переходе это знак ∅.
  Неизвестное решение даёт null в переходе, DECISION_COMPARABLE=0 и
  DECISION_CHANGED=0 (оно не считается установленной сменой решения).
- PD_MODEL и CUTOFF — наиболее частое значение в срезе, при равенстве —
  лексикографически первое. Перестановка продуктов не меняет выбор. Это сводное
  представление; полные множества дополнительно лежат в PD_MODELS_* / CUTOFFS_*.
  Детальный анализ отдельного продукта остаётся в comparison.
- CAUSE=INPUT_DATA/LOGIC/BOTH/NONE — где наблюдались изменения по input_paths и
  logic_paths. BOTH не доказывает изменение стратегии: изменение входов могло
  повлечь изменение выходов. CAUSE_DETAIL — первое совпавшее правило из конфига.
  Для изменений вне обоих наборов CAUSE=NONE, CAUSE_DETAIL=OTHER, HAS_DIFF=1.
- CHANGED_BLOCKS — уникальные блоки первых двух сегментов пути через ';'.
- При проблемах чтения/ключей/глубины COMPARISON_COMPLETE=0: HAS_DIFF=0 и N_DIFFS=0
  тогда не доказывают отсутствие различий. Известные данные одной стороны всё
  равно остаются в разрезах. QUALITY_ISSUE=1 отражает любую диагностику.

## Что дальше

Остались blocks, facts, MartAPI, запуск пяти проверок, summary, ноутбук и интеграция
с платформой. Текущий локальный запуск последовательный; ProcessPool, фоновые
задачи и журналы этапов пока не подключены. pool.filter по-прежнему отклоняется
явно, all/list работают. Этап 4 не меняет REST-контракты фронта.

После успешного запуска у себя:

```bash
git add engine/steps.py engine/run_comparison.py configs/default_spr.yaml tests/test_quality_segments.py BACKEND1_STEP4.md
git diff --cached --stat
git commit -m "Add data quality checks and application segments"
git push
```
