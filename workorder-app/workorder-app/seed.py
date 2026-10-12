"""Load demo data:  python seed.py   (safe to run twice; it skips if data exists)."""
from datetime import date, timedelta

from app import create_app
from app.db import get_db

app = create_app()


def day(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


with app.app_context():
    from app import schemas, services

    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]:
        print("Database already has data - nothing to do.")
        raise SystemExit

    A = lambda **kw: services.create_asset(conn, schemas.AssetCreate(**kw))
    T = lambda **kw: services.create_technician(conn, schemas.TechnicianCreate(**kw))
    W = lambda **kw: services.create_work_order(conn, schemas.WorkOrderCreate(**kw))
    U = lambda pk, **kw: services.update_work_order(conn, pk, schemas.WorkOrderUpdate(**kw))

    pump = A(asset_id="AST-1024", asset_type="Pump", manufacturer="Grundfos", model="CR 32", serial_number="GF-77120",
             usage_hours=18250.5, usage_cycles=4210)
    comp = A(asset_id="AST-1038", asset_type="Compressor", manufacturer="Atlas Copco", model="GA 55", serial_number="AC-55031",
             usage_hours=9120, usage_cycles=1850)
    gen = A(asset_id="AST-1082", asset_type="Generator", manufacturer="Cummins", model="C500", serial_number="CU-90412",
            usage_hours=2310.75, usage_cycles=96, status="OUT_OF_SERVICE")
    A(asset_id="AST-1090", asset_type="Conveyor", manufacturer="Siemens", model="SIMOTICS", serial_number="SI-30077")

    asha = T(name="Asha Rao", skill="Mechanical")
    ben = T(name="Ben Carter", skill="Electrical")
    T(name="Chitra Nair", skill="Hydraulics")
    T(name="Dev Malhotra", skill="Instrumentation", status="ON_LEAVE")

    W(asset_id=pump["id"], maintenance_type_code="INSPECTION", priority="HIGH", technician_id=asha["id"],
      scheduled_date=day(1), description="Quarterly vibration and seal inspection.")
    w2 = W(asset_id=comp["id"], maintenance_type_code="REPAIR", priority="MEDIUM",
           scheduled_date=day(3), description="Replace worn intake filter.")
    w3 = W(asset_id=gen["id"], maintenance_type_code="EMERGENCY_REPAIR", priority="CRITICAL", technician_id=ben["id"],
           scheduled_date=day(0), description="Generator tripped on over-temperature; investigate cooling circuit.")
    U(w3["id"], status="IN_PROGRESS")
    w4 = W(asset_id=pump["id"], maintenance_type_code="SERVICING", priority="LOW", technician_id=asha["id"],
           scheduled_date=day(0), description="Lubrication and alignment check.")
    U(w4["id"], status="IN_PROGRESS")
    U(w4["id"], status="COMPLETED")
    w5 = W(asset_id=comp["id"], maintenance_type_code="INSPECTION", priority="LOW", scheduled_date=day(10))
    U(w5["id"], status="CANCELLED")
    print("Seeded 4 assets, 4 technicians, 5 work orders.")
