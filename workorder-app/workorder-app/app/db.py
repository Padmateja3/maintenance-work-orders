"""SQLite schema and connection handling.

Design notes (also summarised in README.md):
  * 3NF: maintenance types live in their own lookup table (the emergency flag
    belongs to the type, not to each work order).
  * Foreign keys are enforced (PRAGMA foreign_keys=ON) with ON DELETE RESTRICT,
    so history can never be orphaned.
  * Rules 1 and 2 are ALSO enforced by the database (UNIQUE / CHECK) as a safety
    net, in addition to the service layer, which gives friendly errors.
  * Timestamps are ISO-8601 UTC text; scheduled_date is a plain ISO date.
"""
import sqlite3
from contextlib import contextmanager

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id      TEXT    NOT NULL UNIQUE COLLATE NOCASE,          -- business id, e.g. AST-1024
    asset_type    TEXT    NOT NULL,
    manufacturer  TEXT    NOT NULL COLLATE NOCASE,
    model         TEXT    NOT NULL,
    serial_number TEXT    NOT NULL COLLATE NOCASE,
    usage_hours   REAL    NOT NULL DEFAULT 0 CHECK (usage_hours >= 0),
    usage_cycles  INTEGER NOT NULL DEFAULT 0 CHECK (usage_cycles >= 0),
    status        TEXT    NOT NULL DEFAULT 'ACTIVE'
                  CHECK (status IN ('ACTIVE', 'INACTIVE', 'OUT_OF_SERVICE')),
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    UNIQUE (manufacturer, serial_number)
);
CREATE INDEX IF NOT EXISTS idx_assets_status ON assets (status);
CREATE INDEX IF NOT EXISTS idx_assets_type   ON assets (asset_type);

CREATE TABLE IF NOT EXISTS technicians (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    skill      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'ACTIVE'
               CHECK (status IN ('ACTIVE', 'INACTIVE', 'ON_LEAVE')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_technicians_status ON technicians (status);

CREATE TABLE IF NOT EXISTS maintenance_types (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT    NOT NULL UNIQUE,
    name         TEXT    NOT NULL,
    is_emergency INTEGER NOT NULL DEFAULT 0 CHECK (is_emergency IN (0, 1))
);

CREATE TABLE IF NOT EXISTS work_orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_number   TEXT    NOT NULL UNIQUE COLLATE NOCASE,   -- rule 1
    asset_id            INTEGER NOT NULL REFERENCES assets (id)            ON DELETE RESTRICT,
    maintenance_type_id INTEGER NOT NULL REFERENCES maintenance_types (id) ON DELETE RESTRICT,
    description         TEXT    NOT NULL DEFAULT '',
    priority            TEXT    NOT NULL CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    technician_id       INTEGER REFERENCES technicians (id) ON DELETE RESTRICT,
    scheduled_date      TEXT    NOT NULL
                        CHECK (scheduled_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    status              TEXT    NOT NULL DEFAULT 'OPEN'
                        CHECK (status IN ('OPEN', 'ASSIGNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    completed_at        TEXT,
    CHECK (priority <> 'CRITICAL' OR technician_id IS NOT NULL),                        -- rule 2
    CHECK (status NOT IN ('ASSIGNED', 'IN_PROGRESS', 'COMPLETED') OR technician_id IS NOT NULL),
    CHECK ((status = 'COMPLETED') = (completed_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_wo_status           ON work_orders (status);
CREATE INDEX IF NOT EXISTS idx_wo_priority         ON work_orders (priority);
CREATE INDEX IF NOT EXISTS idx_wo_asset_created    ON work_orders (asset_id, created_at);
CREATE INDEX IF NOT EXISTS idx_wo_technician_state ON work_orders (technician_id, status);
CREATE INDEX IF NOT EXISTS idx_wo_scheduled        ON work_orders (scheduled_date);

-- Audit trail: every status change / (re)assignment / edit of a work order.
CREATE TABLE IF NOT EXISTS work_order_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER NOT NULL REFERENCES work_orders (id) ON DELETE CASCADE,
    event_type    TEXT    NOT NULL CHECK (event_type IN ('CREATED', 'STATUS_CHANGED', 'ASSIGNED', 'UPDATED')),
    from_status   TEXT,
    to_status     TEXT,
    technician_id INTEGER REFERENCES technicians (id) ON DELETE RESTRICT,
    note          TEXT,
    created_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_wo ON work_order_events (work_order_id, id);
"""

MAINTENANCE_TYPES = [
    ("INSPECTION", "Inspection", 0),
    ("SERVICING", "Servicing", 0),
    ("REPAIR", "Repair", 0),
    ("OVERHAUL", "Overhaul", 0),
    ("EMERGENCY_REPAIR", "Emergency repair", 1),
]


def _connect(path: str) -> sqlite3.Connection:
    # isolation_level=None -> autocommit; transactions are explicit (see `transaction`).
    conn = sqlite3.connect(path, isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = _connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection):
    """BEGIN IMMEDIATE takes the write lock up front, so read-modify-write
    sequences (like status transitions) cannot interleave."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def init_db(path: str) -> None:
    conn = _connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR IGNORE INTO maintenance_types (code, name, is_emergency) VALUES (?, ?, ?)",
            MAINTENANCE_TYPES,
        )
    finally:
        conn.close()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    init_db(app.config["DATABASE"])
