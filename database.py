import os
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# Normalize Railway / Render connection string from postgres:// to postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
# SQLAlchemy 2.1 domyślnie używa sterownika "psycopg" (v3), a w requirements.txt jest psycopg2-binary.
# Bez tego Railway (adres "postgresql://...") nie wystartuje: "No module named psycopg".
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # Automatically re-establishes dropped connections in cloud environments
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


STARTUP_LOCK_KEY = 4_817_220  # dowolna stała liczba; ta sama we wszystkich kopiach serwera


@contextmanager
def startup_lock():
    """Gdy startuje kilka kopii serwera naraz, tylko jedna na raz tworzy tabele i wgrywa dane startowe.

    Na Postgresie to blokada w bazie (pg_advisory_lock): pozostałe kopie czekają, a potem widzą,
    że dane już są. Na SQLite (lokalnie, jeden proces) nic nie robi.
    """
    if engine.dialect.name != "postgresql":
        yield
        return
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": STARTUP_LOCK_KEY})
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": STARTUP_LOCK_KEY})


def get_db():
    """Dependency providing a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
