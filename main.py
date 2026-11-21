import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from database import engine, Base, SessionLocal, startup_lock
import models  # Registers all models with Base
from services.connectors import ingest_manager
from services.delivery import ensure_delivery_columns, start_worker
from services import runbook_runner
from routers import api, auth, admin, alerts, rules, people, sources, deliveries, runbooks
from seed import seed_all
from services.alert_service import ensure_open_dedup_index
from services.people_service import ensure_people_role_column
from sqlalchemy import inspect, text

# Tabele (SQLite / PostgreSQL) są tworzone niżej, w bloku startowym pod startup_lock()


def ensure_sqlite_columns():
    """Ensures backwards compatibility schema migrations in local SQLite development."""
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE items ADD COLUMN user_id INTEGER REFERENCES users(id)"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE invite_codes ADD COLUMN is_admin_invite BOOLEAN DEFAULT 0"))
            conn.commit()
        except Exception:
            pass
        for col_sql in (
            "ALTER TABLE sources ADD COLUMN enabled BOOLEAN DEFAULT 1",
            "ALTER TABLE sources ADD COLUMN status VARCHAR(20) DEFAULT 'active'",
            "ALTER TABLE sources ADD COLUMN last_error TEXT",
            "ALTER TABLE sources ADD COLUMN last_event_at DATETIME",
            "ALTER TABLE sources ADD COLUMN events_count INTEGER DEFAULT 0",
        ):
            try:
                conn.execute(text(col_sql))
                conn.commit()
            except Exception:
                pass


def ensure_sources_columns(bind) -> None:
    """Adds new Source columns on existing SQLite or PostgreSQL databases."""
    insp = inspect(bind)
    if "sources" not in insp.get_table_names():
        return
    existing = {col["name"] for col in insp.get_columns("sources")}
    is_pg = bind.dialect.name == "postgresql"
    column_ddls = (
        ("enabled", "ALTER TABLE sources ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT TRUE"
         if is_pg else "ALTER TABLE sources ADD COLUMN enabled BOOLEAN DEFAULT 1"),
        ("status", "ALTER TABLE sources ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'"
         if is_pg else "ALTER TABLE sources ADD COLUMN status VARCHAR(20) DEFAULT 'active'"),
        ("last_error", "ALTER TABLE sources ADD COLUMN last_error TEXT"),
        ("last_event_at", "ALTER TABLE sources ADD COLUMN last_event_at TIMESTAMP"
         if is_pg else "ALTER TABLE sources ADD COLUMN last_event_at DATETIME"),
        ("events_count", "ALTER TABLE sources ADD COLUMN events_count INTEGER NOT NULL DEFAULT 0"
         if is_pg else "ALTER TABLE sources ADD COLUMN events_count INTEGER DEFAULT 0"),
    )
    missing = [sql for name, sql in column_ddls if name not in existing]
    if not missing:
        return
    with bind.begin() as conn:
        for sql in missing:
            conn.execute(text(sql))


def purge_demo_user():
    """Removes any obsolete demo accounts from previous iterations."""
    db = SessionLocal()
    try:
        demo = db.query(models.User).filter(
            (models.User.uname == "demo_goldman") | (models.User.email == "demo@goldmansachs.com")
        ).first()
        if demo:
            db.query(models.Item).filter(models.Item.user_id == demo.id).delete()
            db.delete(demo)
            db.commit()
            print("[CLEANUP] Obsolete demo account successfully removed from database.")
    except Exception as e:
        print(f"[CLEANUP ERROR] {e}")
    finally:
        db.close()


def seed_default_teams():
    """Initializes default teams if the table is empty (fully editable by Admin)."""
    db = SessionLocal()
    try:
        if db.query(models.Team).count() == 0:
            default_teams = [
                models.Team(name="Settlements", description="Order settlement workflows and counterparty operations"),
                models.Team(name="Pricing", description="Pricing engine services and market data latency"),
                models.Team(name="Rates", description="Rates trading desk and trade gateway monitoring"),
                models.Team(name="Payments", description="Payments API reliability and regional failover"),
                models.Team(name="Management", description="Executive leadership and platform administration"),
            ]
            db.add_all(default_teams)
            db.commit()
            print("[SEED] Default teams initialized.")
    except Exception as e:
        print(f"[SEED ERROR] {e}")
    finally:
        db.close()


seed_default_departments = seed_default_teams


# Startup initialization & seeding
# Przy kilku kopiach serwera tylko jedna na raz przygotowuje bazę (patrz database.startup_lock)
with startup_lock():
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_columns()
    ensure_sources_columns(engine)
    ensure_delivery_columns(engine)
    ensure_open_dedup_index(engine)
    ensure_people_role_column(engine)
    purge_demo_user()
    seed_default_teams()

    startup_db = SessionLocal()
    try:
        seed_all(startup_db)
        runbook_runner.upgrade_runbook_steps(startup_db)   # stare runbooki -> rodzaje kroków i warunki
    finally:
        startup_db.close()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_delivery_columns(engine)
    start_worker()
    runbook_runner.start_worker()          # Osoba 4: wykonywanie kroków runbooka (jeden worker na kopię)
    await ingest_manager.start()
    try:
        yield
    finally:
        runbook_runner.stop_worker()
        await ingest_manager.stop()


app = FastAPI(
    title="GS Alerting & Orchestration Engine",
    description="Enterprise Ingest -> Rules -> Alerts -> Runbooks -> Escalations Pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication & Administration routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(api.router)

# Alerting system routers (from feature/rules-ui)
for r in (alerts, rules, people, sources, deliveries, runbooks):
    app.include_router(r.router)


@app.get("/health", tags=["System"])
def health_check():
    """Health check endpoint used by Railway / Render uptime monitors."""
    return {"status": "ok"}


# Frontend SPA: Serve compiled React application from frontend/dist
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    if (FRONTEND_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_react_root():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_react_spa(full_path: str):
        if full_path.startswith("api") or full_path in ["docs", "redoc", "openapi.json", "health"]:
            return None
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def api_welcome():
        return {
            "status": "online",
            "message": "Alerting Backend API is operational.",
            "docs": "/docs",
            "frontend_dev_url": "http://localhost:5173"
        }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
