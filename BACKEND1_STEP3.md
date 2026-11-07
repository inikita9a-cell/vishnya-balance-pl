# Бэк 1: загрузка, union, compare

Этот пакет применяется поверх backend1_step2.zip: замените engine/steps.py,
добавьте engine/run_comparison.py, tests/test_comparison.py и эту инструкцию.
Остальные файлы не меняются.

Из корня репозитория (Windows):

```powershell
py -m pip install -r requirements.txt
py -m pytest -q tests
py -m engine.run_comparison --dataset "C:/data/RUN-20260827-0001" --out runs/check_001
```

Замените путь на каталог, содержащий RESULTS/BEFORE_MASTER и RESULTS/AFTER_BETA.
Пути срезов и форматы берутся из configs/default_spr.yaml. Можно передать
--config путь/к/своему.yaml. Путь dataset.path считается относительно текущего
рабочего каталога. Для повторного прогона задайте новое имя --out.

Ожидаемый итог тестов: 14 passed. Проверено на Python 3.12.
Полный датасет здесь недоступен: время на 2002 заявках не измерено.

## Результаты

- union.parquet — вертикальная таблица с SOURCE=BEFORE/AFTER.
- comparison.parquet — outer merge, DIFF_FLAG, четыре CHANGE_TYPE.
- quality.parquet — диагностика чтения и нормализации, ещё не полный s8.
- comparison_status.json — технические числа этого этапа, не финальный summary.json.

Учебный пример: 12 + 14 = 26 строк union, 14 строк comparison,
8 SAME, 4 VALUE_CHANGED, 2 ATTRIBUTE_NEW, всего 6 различий.

## Контракт и обработка ошибок

В engine.steps доступны discover(dataset, pool), load(file, cfg, ...),
union(rows_before, rows_after), check_keys(union_df), compare(union_df, issues=...),
prepare_comparison(cfg, run_dir). Нормализация из этапа 2 сохранена.

Отсутствующий файл: APP_MISSING_BEFORE/AFTER; существующая сторона сравнивается
с пустой. Сломанный файл: PARSE_ERROR; вся пара исключается из витрины.
comparison_status.skipped_parse_app_ids содержит такие заявки.
Дубли ключей: DUPLICATE_KEY; неоднозначный ключ исключается с обеих сторон.
NULL в VALUE означает существующее поле с JSON null; отсутствие атрибута —
настоящий null parquet. Пустая строка сохраняется как пустая строка.

В SOURCE union используются BEFORE/AFTER; отображаемые подписи
BEFORE (MASTER)/AFTER (BETA) относятся к будущему слою facts.
Имена файлов задают APP_ID. Два файла одного ID в одном срезе — явная ошибка.
Каталоги срезов должны существовать. pool all/list поддержаны; filter явно
отклонён до реализации segments. Список может содержать отсутствующий ID:
для него будут две записи APP_MISSING, но не фиктивные строки витрины.

Исключения manifest добавляются к конфигу без изменения исходного объекта.
Ошибки конфигурации/manifest прерывают запуск; ошибки отдельных файлов — нет.
Прогон последовательный, без фонового API, ProcessPool и журнала времени этапов.
В quality пока нет REQUIRED_FIELD_MISSING и DECISION_WITHOUT_REASON.
Следующий этап: полноценное качество данных и segments.
