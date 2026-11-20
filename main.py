import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from database import engine, Base, SessionLocal
from models import Item
from routers import api, views

# Tworzenie tabel bazy danych (SQLite / Postgres)
Base.metadata.create_all(bind=engine)


def seed_initial_data():
    """Wrzuca 2 przykładowe rekordy na start, żeby demo nie było puste."""
    db = SessionLocal()
    try:
        if db.query(Item).count() == 0:
            db.add_all([
                Item(title="Goldman Sachs Group (GS)", category="Equity", value=475.50, description="Kluczowa pozycja benchmarkowa"),
                Item(title="S&P 500 Index Fund", category="Equity", value=512.40, description="Ekspozycja rynkowa"),
                Item(title="US 10Y Treasury Bond", category="Fixed Income", value=100.00, description="Stopa wolna od ryzyka"),
            ])
            db.commit()
    finally:
        db.close()


seed_initial_data()

app = FastAPI(
    title="GS Hackathon Core",
    description="Fullstack FastAPI + React/TSX + SQLite Starter",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes & health check
app.include_router(api.router)


@app.get("/health", tags=["System"])
def health_check():
    """Endpoint używany przez Render/Railway do weryfikacji działania."""
    return {"status": "ok"}


# Obsługa Frontendu: Jeśli zbudowano Reacta w frontend/dist -> serwuj React SPA
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    # Montowanie plików statycznych zbudowanego Reacta
    if (FRONTEND_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_react_spa(full_path: str):
        if full_path.startswith("api") or full_path in ["docs", "redoc", "openapi.json", "health"]:
            return None
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    # Fallback na szablony Jinja2 (gdy frontend React nie został zbudowany)
    app.include_router(views.router)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
