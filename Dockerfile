FROM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=staging DB_DIR=/var/lib/strategylab/db STATIC_DIR=/app/static
WORKDIR /app
COPY requirements.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY engine ./engine
COPY configs ./configs
COPY procedures ./procedures
COPY --from=frontend /src/dist ./static
RUN useradd --uid 1000 --create-home appuser && mkdir -p /var/lib/strategylab/db /var/lib/strategylab/runs /var/lib/strategylab/data && ln -s /var/lib/strategylab/runs /app/runs && ln -s /var/lib/strategylab/data /app/data && chown -R appuser:appuser /var/lib/strategylab
COPY scripts/container_entrypoint.sh /usr/local/bin/container-entrypoint
RUN chmod 755 /usr/local/bin/container-entrypoint
ENTRYPOINT ["/usr/local/bin/container-entrypoint"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/healthz',timeout=3)"
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
