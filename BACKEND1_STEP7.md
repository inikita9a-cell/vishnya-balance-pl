# BACKEND1 — этап 7: Summary / Verdict

## Что изменилось

**Добавляются только новые файлы** (не заменяются `steps.py`, `checks_runner.py`, `mart.py`, `backend/*`, `configs/*`):

```text
engine/summary.py           # расчёт summary из готовых таблиц
engine/run_summary.py       # CLI: py -m engine.run_summary --run runs/check_003
tests/test_summary.py       # 20 тестов
BACKEND1_STEP7.md           # эта инструкция
```

Этап строит `summary.json` для главного экрана аналитика. Он НЕ читает исходные
JSON/XML, НЕ запускает никакой пользовательский Python и не меняет старые Parquet.
На локальном примере 20 тестов этапа прошли. Реальный набор файлов `runs/check_003`
на машине участника доступен только участнику; его следует проверить командами ниже.

## Как запустить у себя (Git Bash, корень репозитория)

1. Распаковать архив в корень проекта — все пути **новые**.
2. Запустить тесты:

```bash
py -m pytest -q tests
```

После 51 предыдущего теста и 20 новых ожидается **71 passed** при неизменившемся
составе тестов. Если тесты изменены другим участником, число может отличаться.

3. Убедиться, что проверки для `check_003` уже отработали (после прошлой правки
   `run_checks(state)` они выполнялись, но можно запустить отдельно):

```bash
py -m engine.run_checks --run runs/check_003
```

4. Рассчитать сводку **поверх уже готового `runs/check_003`**:

```bash
py -m engine.run_summary --run runs/check_003
```

В каталоге появится `runs/check_003/summary.json`. Для контроля:

```bash
py -c "import json; from pathlib import Path; s=json.loads(Path('runs/check_003/summary.json').read_text(encoding='utf-8')); print('apps=',s['total_apps'],'diff=',s['apps_with_diff'],'decision_changed=',s['apps_decision_changed'],'verdict=',s['verdict']['status'],'checks=',s['checks']['status'])"
```

Ожидаемые на известном прогоне **поля, ранее подтверждённые твоим CLI**:
`total_apps = 2002`, `apps_with_diff = 502`, `apps_decision_changed = 385`,
`apps_comparison_incomplete = 0`. Мы специально не зашиваем эти значения в код.
`checks.status = COMPLETE` при наличии `checks.json`.

5. Если вновь перезапускали проверки в готовом прогоне (`checks/rerun`),
   **снова** запускайте `run_summary` — он безопасно обновит `summary.json`
   и скорректирует `summary_seconds` без повторной обработки исходников.

## JSON-контракт для Frontend / Backend 2

`summary.json` — один объект со стабильными ключами (schema_version=1):

| Поле | Тип | Назначение |
|---|---|---|
| `run_id` | string | Имя директории прогона |
| `total_apps` | int | Количество обработанных заявок |
| `apps_with_diff` | int | Заявки с наблюдаемыми различиями |
| `apps_decision_changed` | int | Достоверно сопоставленные заявки со сменой решения |
| `apps_decision_comparable` | int | Заявки с двумя корректными ответами и известными решениями |
| `apps_comparison_incomplete` | int | Неполные сравнения; нулевой diff у них не доказательство равенства |
| `apps_diff_but_decision_same` | int | Есть разница в атрибутах, но решение неизменно |
| `comparison_rows`, `diff_rows` | int | Число сравниваемых строк и различий |
| `approval_rates` | object | `approve_value`, `denominator`, `before_count`, `after_count`, `before_rate`, `after_rate`, `delta_pp` |
| `decision_transitions` | array | `{before,after,count,changed}` (матрица решений) |
| `reason_transitions` | array | `{before,after,count,changed}` (матрица кодов причин, `∅` = нет причины) |
| `decision_distribution` | object | `{before: {decision: count}, after: {...}}` |
| `top_changed_paths` | array | `{path,apps_changed,rows_changed}` |
| `top_changed_blocks` | array | `{block,level,apps_total,apps_changed,share,rows_changed}` |
| `cause_counts` | object | Количество заявок в `NONE`, `LOGIC`, `INPUT_DATA`, `BOTH`, и т. п. |
| `cause_detail_counts` | object | Частоты деталей причин из конфигурации |
| `change_types` | array | `{change_type,rows_changed,apps_changed}`; данные **неаддитивны по типам** |
| `quality` | object | `issues`, `apps_affected`, `by_issue` |
| `checks` | object | `status`, `rows`, `pass`, `fail`, `error`, `checks_selected`, `by_check` |
| `verdict` | object | `status`, `reason_codes`, `disclaimer` |
| `summary_seconds` | float | Время расчёта этой сводки |

**Показатели approval rate** вычисляются только среди корректных пар,
для обеих версий используется **одинаковый знаменатель**.
Значение одобрения приходит из **`segments.approve_value`** в выбранном
YAML-конфиге. Если оно не задано, approval rate = `null`, а не придуманная цифра.

`cause_counts.BOTH` означает, что обнаружены различия и во входных данных,
и в результатах логики. Это **не доказательство двух независимых первопричин**.

`verdict.status` принимает `INCOMPLETE`, `REVIEW_REQUIRED`,
`CHECKS_PENDING`, `NO_CHANGES_OBSERVED`. **Ни одно из этих значений
не является автоматическим разрешением на релиз.**

`checks.status = NOT_RUN`, если `checks.json` ещё нет. Никаких фиктивных PASS.

## Интеграция с платформой: граница ответственности

Наша задача — данные. Для платформенного Backend 2 есть чистая функция:

```python
from engine.summary import prepare_summary
summary = prepare_summary(state['run_dir'], state['cfg'])
```

Её можно вызвать после `run_checks(state)` в оркестраторе платформы.
Это **рекомендация для согласования с Backend 2**, а не патч к её файлам.
Существующий REST endpoint `GET /api/runs/{id}/summary` может читать
`runs/<id>/summary.json` при наличии такого маршрута; точный код REST нам
не передан и потому здесь не меняется.

Команда `py -m engine.run_comparison --dataset ... --out ...` по-прежнему
заканчивается на `facts`. `run_checks` и `run_summary` остаются отдельными
независимо запускаемыми шагами. Для демонстрации CLI:

```bash
py -m engine.run_comparison --dataset "..." --out runs/new_run
py -m engine.run_checks --run runs/new_run
py -m engine.run_summary --run runs/new_run
```

`summary.json` и статистика `summary_*` обновляются атомарной записью.
Поле `comparison_status.json.stage` **не перетирается**, потому что оно
относится к последнему вычислительному этапу основной цепочки.

## Коммит (Conventional Commits)

```bash
git status --short
git add engine/summary.py engine/run_summary.py tests/test_summary.py BACKEND1_STEP7.md
git diff --cached --stat
git commit -m "feat(engine): add verdict summary and decision analytics"
git push origin main
```

Не добавляйте в Git `runs/`, исходный датасет и промежуточные Parquet.
