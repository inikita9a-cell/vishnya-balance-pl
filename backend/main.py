# backend/main.py
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from .db import init_db
from .api import auth, configs, pools, procedures, runs_api, data_api, checks_api, check_apps_api
from .api import explanation_api

app = FastAPI(title="SPR change analysis")
if os.getenv("APP_ENV", "development") == "development":
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

@app.middleware("http")
async def staging_closed(request, call_next):
    if os.getenv("APP_ENV", "development") != "development":
        from .staging_access import protect
        return await protect(request, call_next)
    return await call_next(request)

@app.get("/healthz")
def healthz():
    from sqlalchemy import text
    from .db import engine
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}



@app.on_event("startup")
def _startup():
    init_db()


for r in (auth.router, configs.router, pools.router, procedures.router,
          runs_api.router, data_api.router, checks_api.router,
          check_apps_api.router):
    app.include_router(r)

app.include_router(explanation_api.router)
# Mounted after API routes; unknown API URLs must never return the SPA.
if os.getenv("STATIC_DIR"):
    class SPAFiles(StaticFiles):
        async def get_response(self, path, scope):
            from starlette.exceptions import HTTPException
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404)
            try:
                return await super().get_response(path, scope)
            except HTTPException as exc:
                if exc.status_code != 404 or Path(path).suffix:
                    raise
                return await super().get_response("index.html", scope)
    app.mount("/", SPAFiles(directory=os.environ["STATIC_DIR"], html=True))

