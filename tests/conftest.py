"""Wspólne ustawienia testów.

1) Testy NIGDY nie piszą do prawdziwej bazy app.db. pytest wczytuje ten plik jako pierwszy,
   więc zanim jakikolwiek test zaimportuje `database`, kierujemy go na tymczasową bazę.
2) Każdy plik testowy, który ustawi SEED = {...}, dostaje przed swoimi testami CZYSTĄ bazę
   z danymi z seed_all(**SEED). Dzięki temu pliki nie przeszkadzają sobie nawzajem,
   gdy uruchamiamy wszystkie testy naraz (`pytest`).
"""
import os
import tempfile

import pytest

os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(tempfile.mkdtemp(prefix='gs_tests_'), 'test.db')}"


@pytest.fixture(autouse=True, scope="module")
def _fresh_seeded_db(request):
    seed_kwargs = getattr(request.module, "SEED", None)
    if seed_kwargs is None:
        yield
        return

    from database import Base, SessionLocal, engine
    from seed import seed_all
    from services.alert_service import ensure_open_dedup_index

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ensure_open_dedup_index(engine)
    with SessionLocal() as db:
        seed_all(db, **seed_kwargs)
    yield
