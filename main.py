import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from database import engine, Base, SessionLocal, startup_lock
import models  # Registers all models with Base
from services.security import hash_password
from routers import api, auth, admin, alerts, rules, people, sources, deliveries, runbooks
from seed import seed_all
from sqlalchemy import text

# Tabele (SQLite / PostgreSQL) są tworzone niżej, w bloku startowym pod startup_lock()


def ensure_sqlite_columns():
    """Ensures backwards compatibility schema migrations in local SQLite development."""
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


def seed_default_departments():
    """Initializes default company departments if the table is empty (fully editable by Admin)."""
    db = SessionLocal()
    try:
        if db.query(models.Department).count() == 0:
            default_depts = [
                models.Department(name="Management", description="Executive leadership and strategic planning"),
                models.Department(name="IT", description="Engineering, software architecture, and infrastructure"),
                models.Department(name="Finance", description="Capital markets, quantitative analysis, and treasury"),
                models.Department(name="Sales", description="Institutional client relations and capital raising"),
                models.Department(name="Business", description="Business development and operations"),
            ]
            db.add_all(default_depts)
            db.commit()
            print("[SEED] Default company departments initialized.")
    except Exception as e:
        print(f"[SEED ERROR] {e}")
    finally:
        db.close()


def init_admin_from_env():
    """
    Bootstraps an Administrator account if provided via environment variables (e.g. in Railway):
    - ADMIN_UNAME
    - ADMIN_EMAIL
    - ADMIN_PASSWORD
    - ADMIN_PHONE (optional)
    """
    admin_uname = os.getenv("ADMIN_UNAME")
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if not admin_uname or not admin_email or not admin_password:
        return

    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(
            (models.User.uname == admin_uname.strip()) | (models.User.email == admin_email.strip().lower())
        ).first()

        if not existing:
            admin_user = models.User(
                uname=admin_uname.strip(),
                email=admin_email.strip().lower(),
                hashed_password=hash_password(admin_password),
                dzial="Management",
                is_admin=True,
                nrtel=os.getenv("ADMIN_PHONE")
            )
            db.add(admin_user)
            db.commit()
            print(f"[AUTH] Administrator '{admin_uname}' successfully initialized from environment variables.")
        else:
            if not existing.is_admin:
                existing.is_admin = True
                db.commit()
    finally:
        db.close()


# Startup initialization & seeding
# Przy kilku kopiach serwera tylko jedna na raz przygotowuje bazę (patrz database.startup_lock)
with startup_lock():
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_columns()
    purge_demo_user()
    seed_default_departments()
    init_admin_from_env()

    startup_db = SessionLocal()
    try:
        seed_all(startup_db)
    finally:
        startup_db.close()

app = FastAPI(
    title="GS Alerting & Orchestration Engine",
    description="Enterprise Ingest -> Rules -> Alerts -> Runbooks -> Escalations Pipeline",
    version="1.0.0"
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
            "message": "GS Alerting Backend API is operational.",
            "docs": "/docs",
            "frontend_dev_url": "http://localhost:5173"
        }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
