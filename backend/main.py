# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db import init_db
from .api import auth, configs, pools, procedures, runs_api, data_api, checks_api, check_apps_api

app = FastAPI(title="SPR change analysis")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   allow_credentials=True)


@app.on_event("startup")
def _startup():
    init_db()


for r in (auth.router, configs.router, pools.router, procedures.router,
          runs_api.router, data_api.router, checks_api.router,
          check_apps_api.router):
    app.include_router(r)
