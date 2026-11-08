# backend/db.py
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

DB_DIR = os.getenv("DB_DIR", "./db")
os.makedirs(DB_DIR, exist_ok=True)
DB_URL = f"sqlite:///{os.path.join(DB_DIR, 'app.db')}"

engine = create_engine(DB_URL, connect_args={"check_same_thread": False, "timeout": 30})


def configure_sqlite_engine(target):
    @event.listens_for(target, 'connect')
    def configure(connection, _record):
        cursor = connection.cursor()
        cursor.execute('PRAGMA busy_timeout=30000')
        cursor.close()


configure_sqlite_engine(engine)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401
    # Persistent WAL lets report readers coexist with short progress-log writes.
    with engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA journal_mode=WAL')
    Base.metadata.create_all(engine)
