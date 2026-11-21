import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from database import engine, Base, startup_lock
import models  # noqa: F401  (registers all tables with Base)
from services.connectors import ingest_manager
from services.delivery import start_worker
from routers import auth, admin, alerts, rules, people, sources, deliveries, runbooks

# Create tables on startup (sample data is loaded separately: `python seed.py`).
# With several replicas only one prepares the schema at a time (see database.startup_lock).
with startup_lock():
    Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_worker()
    await ingest_manager.start()
    try:
        yield
    finally:
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

for r in (auth, admin, alerts, rules, people, sources, deliveries, runbooks):
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
