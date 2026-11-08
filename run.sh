#!/usr/bin/env bash
set -e

if [ "${APP_ENV:-development}" = "development" ]; then
  export REPORT_ACCESS="${REPORT_ACCESS:-shared}"
fi

# 1. Бэкенд
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Запускаем бэк в фоне
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 &
BACK_PID=$!

# 2. Фронтенд
cd frontend
npm install
npm run dev &
FRONT_PID=$!

# 3. Ждем завершения
trap "kill $BACK_PID $FRONT_PID" EXIT
wait
