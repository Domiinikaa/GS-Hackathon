"""
Tests verifying that application startup does NOT create mock data and that
`python seed.py` populates mock data idempotently on demand.

Uses isolated temporary SQLite databases (app.db is never touched).

    python tests/test_seed_cli.py
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_py(args: list[str], db_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _table_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        return {
            t: cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            for t in tables
        }
    finally:
        conn.close()


def _index_exists(db_path: Path, name: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (name,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def test_app_startup_creates_no_mock_data() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gs_seed_test_"))
    try:
        db_path = tmp / "clean_startup.db"
        probe = """
import json
from fastapi.testclient import TestClient
import main

with TestClient(main.app) as client:
    out = {
        "health": client.get("/health").json(),
        "teams": client.get("/api/teams").json(),
        "sources": client.get("/api/sources").json(),
        "rules": client.get("/api/rules").json(),
        "runbooks": client.get("/api/runbooks").json(),
        "people": client.get("/api/people").json(),
    }
print(json.dumps(out))
"""
        proc = _run_py(["-c", probe], db_path)
        assert proc.returncode == 0, f"startup failed:\n{proc.stderr}\n{proc.stdout}"
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        assert data["health"] == {"status": "ok"}
        for endpoint in ("teams", "sources", "rules", "runbooks", "people"):
            assert data[endpoint] == [], f"expected empty /api/{endpoint}, got {data[endpoint]}"

        assert _index_exists(db_path, "uq_alerts_open_dedup")
        counts = _table_counts(db_path)
        for table in (
            "departments",
            "sources",
            "rules",
            "runbooks",
            "people",
            "users",
            "alerts",
            "events",
            "deliveries",
            "sim_services",
        ):
            assert table in counts, f"missing table {table}"
            assert counts[table] == 0, f"expected 0 rows in {table}, got {counts[table]}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_seed_cli_populates_mock_data_and_is_idempotent() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gs_seed_test_"))
    try:
        db_path = tmp / "seed_after_startup.db"
        init_proc = _run_py(["-c", "import main"], db_path)
        assert init_proc.returncode == 0, init_proc.stderr

        first = _run_py(["seed.py"], db_path)
        assert first.returncode == 0, f"seed.py failed:\n{first.stderr}\n{first.stdout}"

        counts = _table_counts(db_path)
        assert counts["departments"] == 5
        assert counts["sources"] == 5
        assert counts["rules"] == 4
        assert counts["runbooks"] == 3
        assert counts["people"] == 0

        conn = sqlite3.connect(str(db_path))
        try:
            attached = dict(
                conn.execute(
                    "SELECT r.id, rb.name FROM rules r JOIN runbooks rb ON r.runbook_id = rb.id"
                ).fetchall()
            )
        finally:
            conn.close()
        assert attached == {
            "settlements-prod": "settlement-timeout",
            "anna-payments-critical": "payments-high-error-rate",
            "pricing-warnings": "pricing-warnings",
        }

        second = _run_py(["seed.py"], db_path)
        assert second.returncode == 0, f"second seed.py failed:\n{second.stderr}\n{second.stdout}"
        assert "nothing changed" in second.stdout.lower()

        counts_after = _table_counts(db_path)
        assert counts_after["departments"] == 5
        assert counts_after["sources"] == 5
        assert counts_after["rules"] == 4
        assert counts_after["runbooks"] == 3
        assert counts_after["people"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_seed_cli_works_before_app_startup() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gs_seed_test_"))
    try:
        db_path = tmp / "brand_new.db"
        assert not db_path.exists()

        proc = _run_py(["seed.py"], db_path)
        assert proc.returncode == 0, f"seed.py on empty file failed:\n{proc.stderr}\n{proc.stdout}"
        assert db_path.exists()
        assert _index_exists(db_path, "uq_alerts_open_dedup")

        counts = _table_counts(db_path)
        assert counts["departments"] == 5
        assert counts["sources"] == 5
        assert counts["rules"] == 4
        assert counts["runbooks"] == 3
        assert counts["people"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_create_admin_then_seed_cli_with_people() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gs_seed_test_"))
    try:
        db_path = tmp / "admin_then_seed.db"
        admin_proc = _run_py(
            [
                "create_admin.py",
                "--uname",
                "admin",
                "--email",
                "admin@example.com",
                "--password",
                "Secret123!",
            ],
            db_path,
        )
        assert admin_proc.returncode == 0, f"create_admin.py failed:\n{admin_proc.stderr}\n{admin_proc.stdout}"

        counts_admin = _table_counts(db_path)
        assert counts_admin["departments"] == 1
        assert counts_admin["users"] == 1
        assert counts_admin["people"] == 1
        assert counts_admin["sources"] == 0
        assert counts_admin["rules"] == 0
        assert counts_admin["runbooks"] == 0

        conn = sqlite3.connect(str(db_path))
        try:
            team_name = conn.execute("SELECT name FROM departments").scalar() if hasattr(conn.execute("SELECT name FROM departments"), "scalar") else conn.execute("SELECT name FROM departments").fetchone()[0]
            person_row = conn.execute("SELECT name, team, role FROM people").fetchone()
        finally:
            conn.close()
        assert team_name == "Management"
        assert person_row == ("admin", "Management", "lead")

        seed_proc = _run_py(["seed.py", "--with-people"], db_path)
        assert seed_proc.returncode == 0, f"seed.py --with-people failed:\n{seed_proc.stderr}\n{seed_proc.stdout}"

        counts_seeded = _table_counts(db_path)
        assert counts_seeded["departments"] == 5
        assert counts_seeded["sources"] == 5
        assert counts_seeded["rules"] == 4
        assert counts_seeded["runbooks"] == 3
        assert counts_seeded["people"] == 8  # admin + 3 members + 4 team leads

        seed_again = _run_py(["seed.py", "--with-people"], db_path)
        assert seed_again.returncode == 0, seed_again.stderr
        assert "nothing changed" in seed_again.stdout.lower()

        counts_repeat = _table_counts(db_path)
        assert counts_repeat["departments"] == 5
        assert counts_repeat["sources"] == 5
        assert counts_repeat["rules"] == 4
        assert counts_repeat["runbooks"] == 3
        assert counts_repeat["people"] == 8
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_seed_cli_only_subset() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gs_seed_test_"))
    try:
        db_path = tmp / "only_subset.db"
        proc = _run_py(["seed.py", "--only", "teams", "sources"], db_path)
        assert proc.returncode == 0, f"seed.py --only failed:\n{proc.stderr}\n{proc.stdout}"

        counts = _table_counts(db_path)
        assert counts["departments"] == 5
        assert counts["sources"] == 5
        assert counts["rules"] == 0
        assert counts["runbooks"] == 0
        assert counts["people"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
