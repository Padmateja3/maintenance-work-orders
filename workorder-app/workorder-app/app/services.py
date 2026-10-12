"""Data access + business logic. Every write runs inside one transaction."""
from datetime import date

from . import clock, rules
from .db import transaction
from .errors import ApiError
from .rules import RuleViolation


# =============================================================== helpers ====
def _row_or_404(conn, table: str, pk: int, label: str):
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (pk,)).fetchone()  # table is never user input
    if row is None:
        raise ApiError(404, "NOT_FOUND", f"{label} {pk} not found.")
    return row


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _enum_filter(args, name: str, allowed: tuple[str, ...]) -> list[str]:
    raw = args.get(name)
    if not raw:
        return []
    values = [v.strip().upper() for v in raw.split(",") if v.strip()]
    bad = [v for v in values if v not in allowed]
    if bad:
        raise ApiError(400, "INVALID_FILTER", f"Invalid {name}: {', '.join(bad)}. Allowed: {', '.join(allowed)}.")
    return values


def _int_filter(args, name: str):
    raw = args.get(name)
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except ValueError:
        raise ApiError(400, "INVALID_FILTER", f"{name} must be an integer.")


def _date_filter(args, name: str):
    raw = args.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        raise ApiError(400, "INVALID_FILTER", f"{name} must be a date in YYYY-MM-DD format.")


def _paging(args) -> tuple[int, int]:
    limit = _int_filter(args, "limit")
    offset = _int_filter(args, "offset")
    limit = 50 if limit is None else limit
    offset = 0 if offset is None else offset
    if not 1 <= limit <= 200 or offset < 0:
        raise ApiError(400, "INVALID_FILTER", "limit must be 1-200 and offset must be >= 0.")
    return limit, offset


def _update_sql(table: str, pk: int, changes: dict) -> tuple[str, list]:
    # Column names come from pydantic field names (a fixed whitelist), values are bound.
    cols = ", ".join(f"{k} = ?" for k in changes)
    return f"UPDATE {table} SET {cols}, updated_at = ? WHERE id = ?", [*changes.values(), clock.now_iso(), pk]


# ================================================================ assets ====
def asset_dict(r) -> dict:
    return {k: r[k] for k in (
        "id", "asset_id", "asset_type", "manufacturer", "model", "serial_number",
        "usage_hours", "usage_cycles", "status", "created_at", "updated_at")}


def create_asset(conn, p) -> dict:
    ts = clock.now_iso()
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO assets (asset_id, asset_type, manufacturer, model, serial_number, usage_hours,"
            " usage_cycles, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (p.asset_id, p.asset_type, p.manufacturer, p.model, p.serial_number,
             p.usage_hours, p.usage_cycles, p.status, ts, ts))
    return get_asset(conn, cur.lastrowid)


def get_asset(conn, pk: int) -> dict:
    return asset_dict(_row_or_404(conn, "assets", pk, "Asset"))


def list_assets(conn, args) -> dict:
    where, params = [], []
    statuses = _enum_filter(args, "status", rules.ASSET_STATUSES)
    if statuses:
        where.append(f"status IN ({','.join('?' * len(statuses))})")
        params += statuses
    if args.get("asset_type"):
        where.append("asset_type = ? COLLATE NOCASE")
        params.append(args["asset_type"].strip())
    if args.get("q"):
        like = _like(args["q"].strip())
        where.append("(asset_id LIKE ? ESCAPE '\\' OR serial_number LIKE ? ESCAPE '\\' OR manufacturer LIKE ? ESCAPE '\\'"
                     " OR model LIKE ? ESCAPE '\\' OR asset_type LIKE ? ESCAPE '\\')")
        params += [like] * 5
    limit, offset = _paging(args)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM assets {clause}", params).fetchone()[0]
    rows = conn.execute(f"SELECT * FROM assets {clause} ORDER BY asset_id LIMIT ? OFFSET ?",
                        [*params, limit, offset]).fetchall()
    return {"items": [asset_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


def update_asset(conn, pk: int, p) -> dict:
    changes = p.model_dump(exclude_unset=True)
    with transaction(conn):
        _row_or_404(conn, "assets", pk, "Asset")
        if changes:
            sql, params = _update_sql("assets", pk, changes)
            conn.execute(sql, params)
    return get_asset(conn, pk)


# ========================================================== technicians ====
def technician_dict(r) -> dict:
    return {k: r[k] for k in ("id", "name", "skill", "status", "created_at", "updated_at")}


def create_technician(conn, p) -> dict:
    ts = clock.now_iso()
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO technicians (name, skill, status, created_at, updated_at) VALUES (?,?,?,?,?)",
            (p.name, p.skill, p.status, ts, ts))
    return get_technician(conn, cur.lastrowid)


def get_technician(conn, pk: int) -> dict:
    return technician_dict(_row_or_404(conn, "technicians", pk, "Technician"))


def list_technicians(conn, args) -> dict:
    where, params = [], []
    statuses = _enum_filter(args, "status", rules.TECHNICIAN_STATUSES)
    if statuses:
        where.append(f"status IN ({','.join('?' * len(statuses))})")
        params += statuses
    if args.get("skill"):
        where.append("skill LIKE ? ESCAPE '\\'")
        params.append(_like(args["skill"].strip()))
    if args.get("q"):
        where.append("(name LIKE ? ESCAPE '\\' OR skill LIKE ? ESCAPE '\\')")
        params += [_like(args["q"].strip())] * 2
    limit, offset = _paging(args)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM technicians {clause}", params).fetchone()[0]
    rows = conn.execute(f"SELECT * FROM technicians {clause} ORDER BY name LIMIT ? OFFSET ?",
                        [*params, limit, offset]).fetchall()
    return {"items": [technician_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


def update_technician(conn, pk: int, p) -> dict:
    changes = p.model_dump(exclude_unset=True)
    with transaction(conn):
        _row_or_404(conn, "technicians", pk, "Technician")
        if changes:
            sql, params = _update_sql("technicians", pk, changes)
            conn.execute(sql, params)
    return get_technician(conn, pk)


# ===================================================== maintenance types ====
def list_maintenance_types(conn) -> list[dict]:
    rows = conn.execute("SELECT id, code, name, is_emergency FROM maintenance_types ORDER BY id").fetchall()
    return [{"id": r["id"], "code": r["code"], "name": r["name"], "is_emergency": bool(r["is_emergency"])} for r in rows]


def _resolve_type(conn, type_id, type_code):
    if type_id is not None:
        row = conn.execute("SELECT * FROM maintenance_types WHERE id = ?", (type_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM maintenance_types WHERE code = ?", (type_code,)).fetchone()
    if row is None:
        raise RuleViolation("REFERENCE_NOT_FOUND", "Unknown maintenance type.", field="maintenance_type_id")
    return row


# ========================================================== work orders ====
WO_COLUMNS = """
    wo.*,
    a.asset_id AS a_code, a.asset_type AS a_type, a.manufacturer AS a_mfr, a.model AS a_model, a.status AS a_status,
    mt.code AS mt_code, mt.name AS mt_name, mt.is_emergency AS mt_emergency,
    t.name AS t_name, t.skill AS t_skill, t.status AS t_status
"""
WO_FROM = """
    FROM work_orders wo
    JOIN assets a             ON a.id  = wo.asset_id
    JOIN maintenance_types mt ON mt.id = wo.maintenance_type_id
    LEFT JOIN technicians t   ON t.id  = wo.technician_id
"""
SORTS = {
    "created_at": "wo.created_at",
    "scheduled_date": "wo.scheduled_date",
    "work_order_number": "wo.work_order_number",
    "priority": "CASE wo.priority WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3 WHEN 'MEDIUM' THEN 2 ELSE 1 END",
}


def work_order_dict(r) -> dict:
    return {
        "id": r["id"],
        "work_order_number": r["work_order_number"],
        "asset_id": r["asset_id"],
        "asset": {"id": r["asset_id"], "asset_id": r["a_code"], "asset_type": r["a_type"],
                  "manufacturer": r["a_mfr"], "model": r["a_model"], "status": r["a_status"]},
        "maintenance_type": {"id": r["maintenance_type_id"], "code": r["mt_code"], "name": r["mt_name"],
                             "is_emergency": bool(r["mt_emergency"])},
        "description": r["description"],
        "priority": r["priority"],
        "technician_id": r["technician_id"],
        "technician": None if r["technician_id"] is None else
        {"id": r["technician_id"], "name": r["t_name"], "skill": r["t_skill"], "status": r["t_status"]},
        "scheduled_date": r["scheduled_date"],
        "status": r["status"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "completed_at": r["completed_at"],
        "allowed_transitions": list(rules.allowed_transitions(r["status"])),
    }


def get_work_order(conn, pk: int) -> dict:
    row = conn.execute(f"SELECT {WO_COLUMNS} {WO_FROM} WHERE wo.id = ?", (pk,)).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", f"Work order {pk} not found.")
    return work_order_dict(row)


def list_work_orders(conn, args, forced_asset_pk: int | None = None) -> dict:
    where, params = [], []

    statuses = _enum_filter(args, "status", rules.STATUSES)
    if statuses:
        where.append(f"wo.status IN ({','.join('?' * len(statuses))})")
        params += statuses
    priorities = _enum_filter(args, "priority", rules.PRIORITIES)
    if priorities:
        where.append(f"wo.priority IN ({','.join('?' * len(priorities))})")
        params += priorities

    asset_pk = forced_asset_pk if forced_asset_pk is not None else _int_filter(args, "asset_id")
    if asset_pk is not None:
        where.append("wo.asset_id = ?")
        params.append(asset_pk)
    if args.get("asset_code"):  # business Asset ID, e.g. AST-1024
        where.append("a.asset_id = ?")
        params.append(args["asset_code"].strip())

    technician_pk = _int_filter(args, "technician_id")
    if technician_pk is not None:
        where.append("wo.technician_id = ?")
        params.append(technician_pk)

    if args.get("maintenance_type"):
        where.append("mt.code = ?")
        params.append(args["maintenance_type"].strip().upper())

    d_from, d_to = _date_filter(args, "scheduled_from"), _date_filter(args, "scheduled_to")
    if d_from:
        where.append("wo.scheduled_date >= ?")
        params.append(d_from)
    if d_to:
        where.append("wo.scheduled_date <= ?")
        params.append(d_to)

    if args.get("q"):
        like = _like(args["q"].strip())
        where.append("(wo.work_order_number LIKE ? ESCAPE '\\' OR wo.description LIKE ? ESCAPE '\\'"
                     " OR a.asset_id LIKE ? ESCAPE '\\' OR a.serial_number LIKE ? ESCAPE '\\'"
                     " OR t.name LIKE ? ESCAPE '\\')")
        params += [like] * 5

    sort = args.get("sort") or "-created_at"
    direction = "DESC" if sort.startswith("-") else "ASC"
    key = sort.lstrip("-+ ")
    if key not in SORTS:
        raise ApiError(400, "INVALID_FILTER", f"Invalid sort. Allowed: {', '.join(SORTS)} (prefix with - for descending).")

    limit, offset = _paging(args)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(f"SELECT COUNT(*) {WO_FROM} {clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT {WO_COLUMNS} {WO_FROM} {clause} ORDER BY {SORTS[key]} {direction}, wo.id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset]).fetchall()
    return {"items": [work_order_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


def _next_number(conn) -> str:
    n = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM work_orders").fetchone()[0] + 1000
    while conn.execute("SELECT 1 FROM work_orders WHERE work_order_number = ?", (f"WO-{n}",)).fetchone():
        n += 1
    return f"WO-{n}"


def _require_assignable_technician(conn, technician_id: int):
    tech = conn.execute("SELECT * FROM technicians WHERE id = ?", (technician_id,)).fetchone()
    if tech is None:
        raise RuleViolation("REFERENCE_NOT_FOUND", f"Technician {technician_id} does not exist.", field="technician_id")
    if tech["status"] != "ACTIVE":
        raise RuleViolation("TECHNICIAN_UNAVAILABLE",
                            f"Technician {tech['name']} is {tech['status']} and cannot be assigned.",
                            field="technician_id")
    return tech


def _add_event(conn, wo_id, event_type, *, from_status=None, to_status=None, technician_id=None, note=None):
    conn.execute(
        "INSERT INTO work_order_events (work_order_id, event_type, from_status, to_status, technician_id, note, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (wo_id, event_type, from_status, to_status, technician_id, note, clock.now_iso()))


def create_work_order(conn, p) -> dict:
    with transaction(conn):
        asset = conn.execute("SELECT * FROM assets WHERE id = ?", (p.asset_id,)).fetchone()
        if asset is None:
            raise RuleViolation("REFERENCE_NOT_FOUND", f"Asset {p.asset_id} does not exist.", field="asset_id")
        mtype = _resolve_type(conn, p.maintenance_type_id, p.maintenance_type_code)
        if p.technician_id is not None:
            _require_assignable_technician(conn, p.technician_id)

        rules.check_critical_has_technician(p.priority, p.technician_id)                      # rule 2
        rules.check_schedule_not_in_past(p.scheduled_date, clock.today())                      # rule 5
        rules.check_asset_accepts_maintenance(asset["status"], bool(mtype["is_emergency"]))    # rule 6

        number = p.work_order_number or _next_number(conn)                                     # rule 1 (UNIQUE backs it up)
        status = "ASSIGNED" if p.technician_id is not None else "OPEN"
        ts = clock.now_iso()
        cur = conn.execute(
            "INSERT INTO work_orders (work_order_number, asset_id, maintenance_type_id, description, priority,"
            " technician_id, scheduled_date, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (number, asset["id"], mtype["id"], p.description, p.priority, p.technician_id,
             p.scheduled_date.isoformat(), status, ts, ts))
        _add_event(conn, cur.lastrowid, "CREATED", to_status=status, technician_id=p.technician_id)
    return get_work_order(conn, cur.lastrowid)


def update_work_order(conn, pk: int, p) -> dict:
    sent = p.model_fields_set
    with transaction(conn):
        row = _row_or_404(conn, "work_orders", pk, "Work order")
        current = row["status"]

        # -- immutable identity fields -------------------------------------
        if "asset_id" in sent and p.asset_id != row["asset_id"]:
            raise RuleViolation("IMMUTABLE_FIELD", "The asset of a work order cannot be changed.", field="asset_id")
        if "work_order_number" in sent and (p.work_order_number or "").lower() != row["work_order_number"].lower():
            raise RuleViolation("IMMUTABLE_FIELD", "The work order number cannot be changed.", field="work_order_number")

        # -- proposed new state ---------------------------------------------
        new = {k: row[k] for k in ("maintenance_type_id", "description", "priority", "technician_id", "scheduled_date")}
        if "maintenance_type_id" in sent or "maintenance_type_code" in sent:
            new["maintenance_type_id"] = _resolve_type(conn, p.maintenance_type_id, p.maintenance_type_code)["id"]
        for field in ("description", "priority", "technician_id"):
            if field in sent:
                new[field] = getattr(p, field)
        if "scheduled_date" in sent:
            new["scheduled_date"] = p.scheduled_date.isoformat()

        target = p.status if "status" in sent else None
        if target is not None:
            rules.check_transition(current, target)               # rules 3 & 4, state machine
        changed = {k for k, v in new.items() if v != row[k]}
        if current in rules.TERMINAL and changed:
            raise ApiError(409, "WORK_ORDER_CLOSED", f"A {current} work order can no longer be modified.")

        # -- technician changes ---------------------------------------------
        tech_changed = "technician_id" in changed
        if tech_changed:
            if current not in rules.REASSIGNABLE:
                raise ApiError(409, "INVALID_STATE", f"The technician cannot be changed while the work order is {current}.")
            if new["technician_id"] is not None:
                _require_assignable_technician(conn, new["technician_id"])
        # Assigning a technician to an OPEN work order moves it to ASSIGNED.
        if target is None and current == "OPEN" and tech_changed and new["technician_id"] is not None:
            target = "ASSIGNED"
        final_status = target or current

        # -- rules on the resulting state -------------------------------------
        rules.check_critical_has_technician(new["priority"], new["technician_id"])           # rule 2
        rules.check_status_has_technician(final_status, new["technician_id"])
        if "scheduled_date" in changed:
            rules.check_schedule_not_in_past(date.fromisoformat(new["scheduled_date"]), clock.today())   # rule 5
        if "maintenance_type_id" in changed:  # closes the "create as emergency, then change type" loophole (rule 6)
            asset = conn.execute("SELECT status FROM assets WHERE id = ?", (row["asset_id"],)).fetchone()
            mtype = conn.execute("SELECT is_emergency FROM maintenance_types WHERE id = ?",
                                 (new["maintenance_type_id"],)).fetchone()
            rules.check_asset_accepts_maintenance(asset["status"], bool(mtype["is_emergency"]))

        status_changed = final_status != current
        if not changed and not status_changed:
            return get_work_order(conn, pk)  # nothing to do

        # -- persist ----------------------------------------------------------
        sets = dict(new)
        if status_changed:
            sets["status"] = final_status
            if final_status == "COMPLETED":
                sets["completed_at"] = clock.now_iso()
        sql, params = _update_sql("work_orders", pk, sets)
        conn.execute(sql, params)

        # -- audit trail ------------------------------------------------------
        if status_changed:
            _add_event(conn, pk, "STATUS_CHANGED", from_status=current, to_status=final_status,
                       technician_id=new["technician_id"])
        elif tech_changed:
            _add_event(conn, pk, "ASSIGNED", technician_id=new["technician_id"])
        other = sorted(changed - {"technician_id"})
        if other:
            _add_event(conn, pk, "UPDATED", note="Changed: " + ", ".join(other))
    return get_work_order(conn, pk)


def list_events(conn, pk: int) -> list[dict]:
    _row_or_404(conn, "work_orders", pk, "Work order")
    rows = conn.execute(
        "SELECT e.*, t.name AS t_name FROM work_order_events e"
        " LEFT JOIN technicians t ON t.id = e.technician_id"
        " WHERE e.work_order_id = ? ORDER BY e.id", (pk,)).fetchall()
    return [{"id": r["id"], "event_type": r["event_type"], "from_status": r["from_status"],
             "to_status": r["to_status"], "technician_id": r["technician_id"], "technician_name": r["t_name"],
             "note": r["note"], "created_at": r["created_at"]} for r in rows]


def asset_history(conn, asset_pk: int, args) -> dict:
    asset = get_asset(conn, asset_pk)
    by_status = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, COUNT(*) AS n FROM work_orders WHERE asset_id = ? GROUP BY status", (asset_pk,))}
    last_done = conn.execute(
        "SELECT MAX(completed_at) FROM work_orders WHERE asset_id = ?", (asset_pk,)).fetchone()[0]
    listing = list_work_orders(conn, args, forced_asset_pk=asset_pk)
    return {
        "asset": asset,
        "summary": {"total": sum(by_status.values()), "by_status": by_status, "last_completed_at": last_done},
        **listing,
    }
