# StrategyLab: первый безопасный staging

Облачные ресурсы не созданы. Push/merge не выполнялись. Docker локально отсутствует; контейнерная проверка должна успешно пройти в GitHub Actions до публикации. Настройки без STAGING_USERS_JSON или корректного HTTPS APP_BASE_URL сохраняют 503 для всего, кроме /healthz.

## A. GitHub Actions CI
PR и push в demo/strategylab-staging: полный pytest, npm test/build, docker build, scripts/container_ci.py. Сценарий проверяет закрытый контейнер, персональную аутентификацию, HTML/assets/API/health на одном порту и сохранность SQLite, dataset и результата после удаления и пересоздания контейнера с тем же volume. Данные сценария синтетические; production-секреты не нужны. Pipeline не выполняет деплой и не создаёт облачные ресурсы.

После разрешения на push: дождаться зелёного CI именно на публикуемом commit. Добавить required check verify в защиту demo/strategylab-staging. Не пропускать тесты ради публикации. Python requirements пока не зафиксированы lock-файлом: пересборки могут менять зависимости, откат выполнять на сохранённый образ Render.

## B. Docker production build
Корневой Dockerfile: Node build → Python runtime, FastAPI раздаёт React и /api; /healthz проверяет соединение SQLite. ENTRYPOINT создаёт каталоги на подключённом диске и назначает владельца UID 1000, затем gosu запускает приложение без root. Один worker, один экземпляр. Docker CMD учитывает PORT. Локальные Vite/run.ps1/run.sh сохраняются; frontend/Dockerfile обслуживает существующий Compose.

## C. Постоянное хранилище
Диск /var/lib/strategylab: db/app.db, runs/, data/. /app/runs и /app/data — ссылки на диск. Новый пустой диск инициализируется при старте. Импортированные файлы должны читаться UID 1000; БД и результаты должны быть доступны ему для записи. Не создавать ссылки, выходящие за разрешённые каталоги. Датасеты — общий доверенный набор команды, загружаемый администратором отдельно; API загрузки отсутствует. Runs и конфиги принадлежат индивидуальному пользователю.

Данные запрещены в Git/image. Не переносить локальные demo cookies/имена как действующую идентичность. При импорте результатов явно сопоставить started_by/owner с утверждёнными логинами; неизвестные владельцы не получают автоматического доступа.

CI пересоздаёт контейнер и проверяет три типа состояния. На Render обязательно повторить проверку с тестовым запуском и Manual Deploy перед выдачей ссылки. Диск вызывает перерыв в обслуживании при деплое; остановить новые запуски и дождаться фоновых задач. Резервировать SQLite через backup API, результаты копировать при остановленных заданиях. Хранить защищённую копию вне диска Render, проверить восстановление.

## D. Аутентификация и аудит маршрутов
Минимальная защита: HTTPS Basic с отдельным логином и случайным паролем минимум 24 символа на человека. STAGING_USERS_JSON — явный allowlist логинов и scrypt salt:hash; пароли выдаются лично через менеджер паролей. scripts/staging_credentials.py читает пароль скрыто и выводит только JSON записи. Объединить записи в один JSON-объект. Не использовать общую учётку команды. Это проверка владения персональным секретом, не подтверждение корпоративного email; OIDC/MFA остаётся возможным следующим шагом, но сейчас не требуется.

FastAPI middleware проверяет ВСЕ URL независимо от Host, включая прямой onrender.com, HTML/assets/docs/openapi и неизвестные URL. Исключение: GET /healthz без данных. Без настроек 503; неверные credentials 401. Cookie spr_user и forwarded identity headers не доверяются. Изменяющие запросы требуют Origin, точно совпадающий с APP_BASE_URL. CLI-клиенты должны передавать его явно. HTTPS обеспечивает Render; локальный HTTP smoke не моделирует TLS.

Браузер хранит Basic credentials: надёжного программного logout у Basic нет. В staging кнопка смены пользователя скрыта; используйте отдельный профиль/приватное окно и полностью закройте его после демонстрации. Для отзыва доступа удалить пользователя из STAGING_USERS_JSON и перезапустить сервис. MFA и отдельного rate limiter нет: обязательны длинные случайные пароли, малый allowlist и контроль доступа к Render. Никакие passwords/Authorization не логировать.

Маршруты и исправления:
- /api/login: только локально имя; staging возвращает проверенную личность, не принимает смену имени. /me использует middleware identity. /logout не отменяет Basic credentials.
- configs: list/create привязаны к owner, update/duplicate проверяют owner; чужой config нельзя запустить.
- pools/procedures: list/create привязаны к owner. /procedures/{pid}/try запрещён в staging до чтения файла; локально проверяются owner процедуры и run.
- runs: список только собственный. Все /runs/{rid}/... (status, steps, rerun, report, checks, raw, pivot, drilldown, apps, summary, blocks, quality, sankey, explorer) через current_user проверяют started_by до работы с файлами. Чужие ресурсы возвращают 404.
- Идентификаторы и resolved paths ограничены каталогом runs; проверяются symlink escapes. raw app_id проверяется до первого чтения; fallback разрешён только под data. Перед запуском dataset, стороны и manifest ограничены data и проверяются ссылки.
- HTML-отчёт получает sandbox CSP, исключающий исполнение скриптов в origin приложения. SQL analytics использует allowlist колонок и параметры значений.

Python: sandbox.execute_user_code запрещён в staging. Pipeline/checks rerun проходит platform_checks_adapter: overrides, code/path/file и неизвестные check IDs отклоняются; разрешены только 5 встроенных immutable checks. checks_service дополнительно запрещает загрузку модулей вне встроенного каталога. Это доверенный код образа, не sandbox. Пользовательские процедуры не запускаются даже после входа. Не ставить APP_ENV=demo/strategylab-stagingment на Render.

Security tests проверяют каждый зарегистрированный API-маршрут без входа, чужие runs, config duplicate/start, подделку cookie, неверный пароль, неизвестного пользователя, CSRF, Python и path traversal. Они не заменяют будущий аудит при добавлении новых маршрутов/движков.

## E. Render: конкретный checklist (только после разрешения)
1. Создание платного сервиса/диска требует отдельного разрешения. Опубликовать проверенный commit в demo/strategylab-staging, дождаться зелёного CI и container persistence test.
2. Render Dashboard → New → Web Service → подключить нужный GitHub repository. Branch: demo/strategylab-staging; Language/Runtime: Docker; Root Directory: оставить пустым; Dockerfile Path: ./Dockerfile; Docker Build Context: .; Docker Command: пусто (использовать CMD).
3. Name: strategylab-staging (либо свободное имя); выбрать согласованный регион, платный instance с достаточной памятью для pandas/датасета; Instances: 1. Не использовать Free для persistent disk.
4. Advanced → Add Disk: mount /var/lib/strategylab; размер по объёму исходников + результатов + запас. Health Check Path: /healthz. Auto-Deploy: Off.
5. Environment: APP_ENV=staging; PORT=8000; DB_DIR=/var/lib/strategylab/db; STATIC_DIR=/app/static. Секрет STAGING_USERS_JSON пока НЕ задавать. Create Web Service запускает первый deploy, но приложение останется закрытым 503.
6. После успешного закрытого deploy скопировать реальный HTTPS URL вверху сервиса, например https://strategylab-staging.onrender.com. В Environment установить APP_BASE_URL точно равным этому origin без пути; добавить STAGING_USERS_JSON с персональными scrypt-хешами. Save, rebuild/deploy. Не задавать secrets как VITE_* или Docker ARG.
7. Загрузить разрешённые датасеты отдельно через SSH/SCP Render в /var/lib/strategylab/data (не git). Проверить владельца/права. Создать конфиг с dataset.path=/app/data/<dataset>, before_dir/after_dir относительно него. Использовать только встроенные checks.
8. В приватном окне открыть URL: браузер требует логин/пароль. /api/me показывает этот логин; /healthz отвечает 200. Проверить без credentials 401 на UI/API/docs; проверить чужие данные второй учёткой, Python try → 403, frontend загружает assets и /api без другого домена.
9. Создать тестовый анализ, сохранить ID и сверить результат. Manual Deploy → Deploy latest commit. Снова проверить тот же run, SQLite записи и исходный dataset. Убедиться, что не потеряны результаты; проверить backup/restore. До этого ссылку заказчику не выдавать.
10. Settings → Auto-Deploy → After CI Checks Pass. Полученная HTTPS ссылка постоянна, пока существует сервис. Передать ссылку команде/заказчику; персональные пароли — отдельным защищённым каналом.

Откат: выключить auto-deploy, дождаться задач, сделать backup, Deploys → прежний успешный deploy → Rollback. Повторить auth/health/read checks. Откат образа не откатывает диск/схему SQLite; при несовместимой схеме требуется отдельное проверенное восстановление backup. Повторно включать auto-deploy только после исправления.

Официальные инструкции: https://render.com/docs/web-services https://render.com/docs/docker https://render.com/docs/disks https://render.com/docs/deploys https://render.com/docs/rollbacks


## First demo and credentials
Only explicitly approved synthetic datasets and existing local reports may be imported. Do not copy the working database: import approved Config/Run records with owner/started_by mapped to individual logins, and matching runs/<id> artifacts. No production data. Test user procedures locally; staging procedure_runtime forbids execution.

Generate a personal password locally: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Save it in a password manager, then run `python scripts/staging_credentials.py`. Combine the resulting entries into STAGING_USERS_JSON. Never commit either passwords or credential JSON.

Post-deploy checks (curl prompts for the password with `-u LOGIN`):
```sh
curl -i https://SERVICE.onrender.com/healthz
# 200
curl -i https://SERVICE.onrender.com/
# 503 before auth configuration; 401 after configuration
curl -i https://SERVICE.onrender.com/api/me
curl -i https://SERVICE.onrender.com/docs
# Both 401
curl -i -u LOGIN https://SERVICE.onrender.com/api/me
# 200, personal identity
curl -i -u LOGIN https://SERVICE.onrender.com/api/unknown
# 404
curl -i -u LOGIN -X POST -H 'Origin: https://SERVICE.onrender.com' -H 'Content-Type: application/json' -d '{}' https://SERVICE.onrender.com/api/procedures/1/try
# 403
curl -i -u LOGIN -X POST -H 'Content-Type: application/json' -d '{}' https://SERVICE.onrender.com/api/login
# 403: no Origin
```
Open an approved existing report as its owner (200) and another user (404). Verify React assets and API on the same origin. Redeploy manually and verify the same report ID, database records and data files persist before sharing the URL.
