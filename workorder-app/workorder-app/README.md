# Maintenance Work Order Management

A small full-stack app for registering assets and technicians, raising maintenance work orders, assigning
technicians, tracking status, searching/filtering, and viewing maintenance history.

**Stack:** Python 3.10+ · Flask · SQLite (stdlib `sqlite3`, raw SQL) · pydantic v2 (request validation) ·
plain HTML/CSS/JS frontend (no build step) · `unittest` for tests.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python seed.py                     # optional demo data
python run.py                      # http://127.0.0.1:8000
python -m unittest -v              # run the tests (39)
```

The database file `workorders.db` is created on first start. Set `WORKORDER_DB=/path/to/file.db` to put it elsewhere.

## Project layout

```
app/
  db.py         schema (DDL with constraints + indexes), connections, transaction helper
  rules.py      PURE business rules + state machine (no Flask, no DB)  <- start reading here
  schemas.py    request validation (pydantic)
  services.py   queries + write operations; every write is one transaction
  routes.py     thin HTTP layer
  errors.py     uniform JSON errors
  clock.py      injectable "today" / "now" (so rule 5 is testable)
static/         the UI (index.html, app.js, styles.css)
tests/          test_rules.py (unit) · test_api.py (end-to-end, real SQLite file)
seed.py         demo data
```

## Data model

```
ASSET 1 ──< N WORK_ORDER N >── 1 MAINTENANCE_TYPE
                  │ N
                  └── 0..1 TECHNICIAN          WORK_ORDER 1 ──< N WORK_ORDER_EVENT (audit trail)
```

| Table | Notes |
|---|---|
| `assets` | `id` (PK) + business `asset_id` (UNIQUE, case-insensitive). `UNIQUE(manufacturer, serial_number)`. `CHECK` usage >= 0 and status in (`ACTIVE`, `INACTIVE`, `OUT_OF_SERVICE`). |
| `technicians` | name, skill, status (`ACTIVE`, `INACTIVE`, `ON_LEAVE`). |
| `maintenance_types` | Lookup table (3NF): `code`, `name`, **`is_emergency`**. Seeded: Inspection, Servicing, Repair, Overhaul, Emergency repair. |
| `work_orders` | FKs to asset / type / technician (`ON DELETE RESTRICT`, foreign keys enforced). `work_order_number` UNIQUE. `completed_at` only set when COMPLETED. |
| `work_order_events` | One row per creation / status change / reassignment / edit. Powers the history panel on the detail screen. |

**Indexes:** `work_orders(status)`, `(priority)`, `(asset_id, created_at)`, `(technician_id, status)`, `(scheduled_date)`,
`work_order_events(work_order_id, id)`, plus status/type indexes on assets and technicians.

**Why the emergency flag is on the type:** Rule 6 asks whether "the maintenance type is explicitly marked as an
emergency". Storing that on `maintenance_types` means it is defined once, not repeated (and possibly inconsistent) on every work order.

## Business rules — and where each is enforced

| # | Rule | Service layer (friendly error) | Database (safety net) |
|---|---|---|---|
| 1 | Unique work order number | `409 DUPLICATE_WORK_ORDER_NUMBER` | `UNIQUE`, case-insensitive |
| 2 | CRITICAL needs a technician | `422 CRITICAL_REQUIRES_TECHNICIAN` — on create **and** on update (can't escalate to CRITICAL or unassign a CRITICAL order) | `CHECK (priority <> 'CRITICAL' OR technician_id IS NOT NULL)` |
| 3 | COMPLETED can't return to OPEN | `409 INVALID_TRANSITION`; completed orders are read-only (`409 WORK_ORDER_CLOSED`) | `CHECK` ties `completed_at` to COMPLETED |
| 4 | CANCELLED can't move to IN_PROGRESS | `409 INVALID_TRANSITION` | — |
| 5 | No scheduled date in the past | `422 SCHEDULE_IN_PAST` — on create, and when rescheduling | date-format `CHECK` |
| 6 | OUT_OF_SERVICE asset: emergency types only | `422 ASSET_OUT_OF_SERVICE` — on create, **and when changing the type later** (otherwise: create as emergency, switch to Repair) | — |

State machine (forward-only; COMPLETED and CANCELLED are terminal):

```
OPEN ──> ASSIGNED ──> IN_PROGRESS ──> COMPLETED
  │          │
  └──────────┴──────> CANCELLED
```

All writes use `BEGIN IMMEDIATE`, so two concurrent requests cannot both pass a check against stale state
(covered by `ConcurrencyTests`).

## API

All bodies are JSON. List endpoints return `{"items": [...], "total", "limit", "offset"}` (default `limit` 50, max 200).

| Method & path | Purpose |
|---|---|
| `POST /api/assets` · `GET /api/assets` · `GET /api/assets/{id}` · `PUT /api/assets/{id}` | Assets. List filters: `status`, `asset_type`, `q` |
| `GET /api/assets/{id}/history` | Maintenance history: asset + summary (counts by status, last completed) + its work orders (same filters as the work-order list) |
| `POST /api/technicians` · `GET /api/technicians` · `GET /api/technicians/{id}` · `PUT /api/technicians/{id}` | Technicians. List filters: `status`, `skill`, `q` |
| `GET /api/maintenance-types` | Lookup list |
| `POST /api/work-orders` · `GET /api/work-orders` · `GET /api/work-orders/{id}` · `PUT /api/work-orders/{id}` | Work orders |
| `GET /api/work-orders/{id}/events` | Audit trail of one work order |

**Work-order list filters** (combine freely): `status`, `priority` (comma-separated allowed, e.g. `status=OPEN,ASSIGNED`),
`asset_id` (internal numeric id), `asset_code` (business id, e.g. `AST-1024`), `technician_id`, `maintenance_type` (code),
`scheduled_from` / `scheduled_to` (`YYYY-MM-DD`), `q` (searches number, description, asset id, serial, technician name),
`sort` (`created_at`, `scheduled_date`, `work_order_number`, `priority`; prefix `-` for descending), `limit`, `offset`.
Invalid filter values return `400`.

**Field naming:** on a work order, `asset_id` is the asset's *internal* id (as in `GET /api/work-orders?asset_id=123`); the
nested `asset.asset_id` is the business Asset ID.

**Creating a work order** takes `asset_id`, `priority`, `scheduled_date`, a maintenance type (`maintenance_type_id` **or**
`maintenance_type_code`), and optionally `description`, `technician_id`, `work_order_number` (generated as `WO-1001`… if omitted).
Passing a technician creates it directly as `ASSIGNED`.

**Updating** (`PUT`) only changes the fields you send. Moving status: `{"status": "IN_PROGRESS"}`. Assigning a technician to an
OPEN order moves it to ASSIGNED automatically. `asset_id` and `work_order_number` are immutable. Responses include
`allowed_transitions`, which the UI uses to offer only legal actions.

**Errors** always look like:

```json
{"error": {"code": "ASSET_OUT_OF_SERVICE", "message": "…", "details": [{"field": "maintenance_type_id", "message": "…"}]}}
```
`400` bad JSON/filter · `404` not found · `409` conflict (duplicate, illegal transition, closed order) · `422` validation / business rule.

### Try it with curl

```bash
curl -X POST localhost:8000/api/work-orders -H 'Content-Type: application/json' \
  -d '{"asset_id":1,"maintenance_type_code":"INSPECTION","priority":"HIGH","scheduled_date":"2030-01-15","technician_id":1}'

curl 'localhost:8000/api/work-orders?status=ASSIGNED&priority=HIGH'
curl -X PUT localhost:8000/api/work-orders/1 -H 'Content-Type: application/json' -d '{"status":"IN_PROGRESS"}'
```

## UI

Hash-routed single page: **Work order list** (search + status/priority filters, paging) · **Create** form (warns
about out-of-service assets and CRITICAL-needs-technician before you submit) · **Detail** (all fields, progress
indicator, only the valid actions, audit history) · plus a small **Assets & technicians** page for registration and an
asset **maintenance history** view. All API data is rendered via `textContent`, never `innerHTML`.

## Assumptions and known limitations

* **Assumptions where the brief was silent:** asset statuses are `ACTIVE/INACTIVE/OUT_OF_SERVICE` (only OUT_OF_SERVICE
  restricts anything); only `ACTIVE` technicians can be assigned; no un-assigning once ASSIGNED (cancel or reassign instead);
  technician can't change once IN_PROGRESS; "maintenance history" = all work orders for an asset with a summary.
* **"Today" for rule 5** is the *server's* local date. A per-user time zone would need the client to send its date or zone.
* No authentication/authorisation, no DELETE endpoints, no soft-delete. Fine for the exercise, not for production.
* Marking an asset OUT_OF_SERVICE doesn't touch work orders that already exist; completing a work order doesn't update the asset's usage counters.
* SQLite and Flask's dev server are for the exercise; production would use Postgres + migrations + a WSGI server.
