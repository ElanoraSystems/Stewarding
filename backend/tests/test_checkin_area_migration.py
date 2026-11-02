"""The check-in area moved from the locations to the organization; an area somebody had set must survive the move."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def alembic(db_file, *args):
    env = {**os.environ, "STW_DATABASE_URL": f"sqlite:///{db_file}"}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True, check=True)


def test_the_first_location_area_becomes_the_organizations_and_the_location_columns_go(tmp_path):
    db_file = tmp_path / "m.db"
    alembic(db_file, "upgrade", "a1c5e9b3d7f2")
    conn = sqlite3.connect(db_file)
    conn.execute("DELETE FROM organization")
    conn.execute("INSERT INTO location (code, name, kind, timezone, active, latitude, longitude, geofence_radius_m) VALUES ('A', 'Alpha', 'kitchen', 'Asia/Kuwait', 1, 29.37, 47.97, 150)")
    conn.execute("INSERT INTO location (code, name, kind, timezone, active) VALUES ('B', 'Beta', 'kitchen', 'Asia/Kuwait', 1)")
    conn.commit()
    conn.close()
    alembic(db_file, "upgrade", "head")
    conn = sqlite3.connect(db_file)
    assert conn.execute("SELECT latitude, longitude, geofence_radius_m FROM organization WHERE id = 1").fetchone() == (29.37, 47.97, 150)
    assert "latitude" not in [row[1] for row in conn.execute("PRAGMA table_info(location)")]
    conn.close()
