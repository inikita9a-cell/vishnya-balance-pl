# backend/models.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from .db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Config(Base):
    __tablename__ = "configs"
    id = Column(Integer, primary_key=True)
    owner = Column(String, index=True)
    name = Column(String)
    yaml = Column(Text)  # конфиг целиком, пресет
    created_at = Column(DateTime, default=datetime.utcnow)


class Pool(Base):
    __tablename__ = "pools"
    id = Column(Integer, primary_key=True)
    owner = Column(String, index=True)
    name = Column(String)
    payload = Column(Text)  # JSON: {mode, app_ids, filter}


class Procedure(Base):
    __tablename__ = "procedures"
    id = Column(Integer, primary_key=True)
    owner = Column(String, index=True)
    kind = Column(String)  # normalize|flatten|check|...
    source = Column(String)  # file|workspace
    path = Column(String, nullable=True)  # если file
    code = Column(Text, nullable=True)  # если workspace
    created_at = Column(DateTime, default=datetime.utcnow)


class Run(Base):
    __tablename__ = "runs"
    id = Column(String, primary_key=True)  # uuid
    config_id = Column(Integer, ForeignKey("configs.id"))
    config_snapshot = Column(Text)  # YAML на момент запуска
    started_by = Column(String)
    status = Column(String, default="queued")  # queued|running|done|failed
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)


class StageLog(Base):
    __tablename__ = "stage_logs"
    id = Column(Integer, primary_key=True)
    run_id = Column(String, index=True)
    step = Column(String)
    status = Column(String)  # running|done|failed
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    progress = Column(Integer, default=0)
    rows_in = Column(Integer, nullable=True)
    rows_out = Column(Integer, nullable=True)
    message = Column(Text, nullable=True)
    code_snapshot = Column(Text, nullable=True)  # inspect.getsource + override
    params = Column(Text, nullable=True)  # JSON параметров шага
    started_by = Column(String)


class CheckResult(Base):
    __tablename__ = "check_results"
    id = Column(Integer, primary_key=True)
    run_id = Column(String, index=True)
    check_id = Column(String)
    label = Column(String)
    result = Column(String)  # PASS|FAIL|ERROR
    row = Column(Text)  # JSON полной строки
    created_at = Column(DateTime, default=datetime.utcnow)
