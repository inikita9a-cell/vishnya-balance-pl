# README — запуск

## Быстрый старт (Docker)
docker compose up --build
- Backend: http://localhost:8000/docs
- Frontend: http://localhost:5173

## Локально
./run.sh (Linux/macOS) и .\run.ps1 (Windows).

## Первые шаги
1. Открыть фронт → ввести имя (cookie).
2. Configs → создать пресет (или взять `configs/default_spr.yaml`).
3. Runs → «Запустить» → наблюдать этапы (кто/время/строки/код).
4. Проверки → «Перезапустить только проверки» → обновится `checks.json`.
5. «Скачать HTML-протокол» → `runs/<id>/report.html`.

## Песочница
`POST /api/procedures` (workspace|file) → `POST /api/procedures/{id}/try`.
Контракт: функция `entry(mart=None, app_ids=[], params={}) -> dict|list`.
Таймаут 30 с, subprocess, ошибка → в журнал, приложение живо.

## Что в TODO
- Полные тела s3, s7, s9, s11 (flatten/compare/segments/facts) — блок 1.
- Mart.segments() — пробросить run_dir.
- LLM-блок на фронте — скрыт без LLM_API_KEY.