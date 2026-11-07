# Мини-фикс Pivot / Drill-down: SQL NULL и pandas NaN

Причина падения `test_click_every_cell_exactly_matches_pivot`:
NULL в измерении `CAUSE` приходит из DuckDB через pandas как `float("nan")`.
`pivot()` показывал `CNT=1`, но переданный в `drilldown()` фильтр по NaN не совпадал с SQL NULL.

Изменены ТОЛЬКО `backend/duck.py` и `tests/test_duck_pivot.py`:
- нормализация отсутствующих значений в результатах `pivot()` (JSON null, а не NaN);
- SQL IS NULL для None / NaN / pandas.NA в одиночных и списочных фильтрах;
- два дополнительных регрессионных теста.

## Применение (из корня репозитория, после git pull)

Скопируйте `pivot_null_fix.patch` из архива в корень репозитория.
```bash
git apply --check pivot_null_fix.patch
git apply pivot_null_fix.patch
py -m pytest -q tests
```

Не перезаписывайте `backend/duck.py` вручную, если он уже менялся параллельно. Если `git apply --check` не проходит — сравните изменения и согласуйте вручную.

Перед коммитом:
```bash
git diff --check
git diff -- backend/duck.py tests/test_duck_pivot.py
git add backend/duck.py tests/test_duck_pivot.py
git commit -m "fix(pivot): match null dimensions in drilldown"
git push origin main
```

Ни `runs/`, ни исходные JSON добавлять в git не нужно.
