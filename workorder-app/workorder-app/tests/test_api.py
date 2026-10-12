"""End-to-end API tests against a real (temporary) SQLite file."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone

from app import create_app

TODAY = date(2026, 10, 12)
PAST, FUTURE = "2026-10-11", "2026-11-01"


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.app = create_app({
            "DATABASE": self.db_path,
            "TESTING": True,
            "TODAY_FN": lambda: TODAY,
            "NOW_FN": lambda: datetime(2026, 10, 12, 9, 30, tzinfo=timezone.utc),
        })
        self.c = self.app.test_client()
        self._n = 0

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- helpers ----------------------------------------------------------
    def asset(self, **kw):
        self._n += 1
        body = {"asset_id": f"AST-{self._n}", "asset_type": "Pump", "manufacturer": "Acme",
                "model": "P-100", "serial_number": f"SN-{self._n}", **kw}
        r = self.c.post("/api/assets", json=body)
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def tech(self, **kw):
        body = {"name": "Asha", "skill": "Mechanical", **kw}
        r = self.c.post("/api/technicians", json=body)
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def wo_body(self, asset, **kw):
        return {"asset_id": asset["id"], "maintenance_type_code": "INSPECTION",
                "priority": "MEDIUM", "scheduled_date": FUTURE, **kw}

    def wo(self, asset, expect=201, **kw):
        r = self.c.post("/api/work-orders", json=self.wo_body(asset, **kw))
        self.assertEqual(r.status_code, expect, r.get_json())
        return r.get_json()

    def put(self, wo_id, expect=200, **kw):
        r = self.c.put(f"/api/work-orders/{wo_id}", json=kw)
        self.assertEqual(r.status_code, expect, r.get_json())
        return r.get_json()


# =========================================================== registration ===
class RegistrationTests(ApiTestCase):
    def test_asset_crud(self):
        a = self.asset(usage_hours=12.5, usage_cycles=3)
        self.assertEqual(a["status"], "ACTIVE")
        self.assertEqual(self.c.get(f"/api/assets/{a['id']}").get_json()["usage_hours"], 12.5)
        r = self.c.put(f"/api/assets/{a['id']}", json={"usage_hours": 20, "status": "out_of_service"})
        self.assertEqual(r.get_json()["status"], "OUT_OF_SERVICE")
        self.assertEqual(r.get_json()["usage_hours"], 20)
        self.assertEqual(len(self.c.get("/api/assets").get_json()["items"]), 1)

    def test_duplicate_asset_id_and_serial(self):
        a = self.asset()
        r = self.c.post("/api/assets", json={
            "asset_id": a["asset_id"].lower(), "asset_type": "Pump", "manufacturer": "Other",
            "model": "x", "serial_number": "OTHER"})                          # same Asset ID, different case
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["error"]["code"], "DUPLICATE_ASSET_ID")
        r = self.c.post("/api/assets", json={
            "asset_id": "AST-NEW", "asset_type": "Pump", "manufacturer": "ACME",
            "model": "x", "serial_number": a["serial_number"].lower()})
        self.assertEqual(r.get_json()["error"]["code"], "DUPLICATE_SERIAL_NUMBER")

    def test_asset_validation(self):
        r = self.c.post("/api/assets", json={"asset_id": "", "usage_hours": -1, "bogus": 1})
        self.assertEqual(r.status_code, 422)
        fields = {d["field"] for d in r.get_json()["error"]["details"]}
        self.assertTrue({"asset_id", "asset_type", "usage_hours", "bogus"} <= fields)

    def test_technician_crud_and_filters(self):
        t1 = self.tech(name="Asha", skill="Electrical")
        self.tech(name="Ben", skill="Hydraulics", status="ON_LEAVE")
        self.assertEqual(self.c.get(f"/api/technicians/{t1['id']}").get_json()["name"], "Asha")
        self.assertEqual(self.c.get("/api/technicians?status=ON_LEAVE").get_json()["total"], 1)
        self.assertEqual(self.c.get("/api/technicians?skill=hydra").get_json()["total"], 1)

    def test_404s_and_bad_json(self):
        self.assertEqual(self.c.get("/api/assets/999").status_code, 404)
        self.assertEqual(self.c.get("/api/technicians/999").status_code, 404)
        self.assertEqual(self.c.get("/api/work-orders/999").status_code, 404)
        r = self.c.post("/api/assets", data="not json", content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"]["code"], "INVALID_JSON")


# ================================================================ rules ====
class RuleTests(ApiTestCase):
    def test_rule1_unique_work_order_number(self):
        a = self.asset()
        self.wo(a, work_order_number="WO-TEST-1")
        r = self.c.post("/api/work-orders", json=self.wo_body(a, work_order_number="wo-test-1"))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["error"]["code"], "DUPLICATE_WORK_ORDER_NUMBER")

    def test_generated_numbers_are_unique_and_skip_manual_ones(self):
        a = self.asset()
        self.wo(a, work_order_number="WO-1002")  # collides with the next generated number
        numbers = [self.wo(a)["work_order_number"] for _ in range(3)]
        self.assertEqual(len(set(numbers)), 3)
        self.assertNotIn("WO-1002", numbers)

    def test_rule2_critical_requires_technician_on_create(self):
        a, t = self.asset(), self.tech()
        err = self.wo(a, expect=422, priority="CRITICAL")["error"]
        self.assertEqual(err["code"], "CRITICAL_REQUIRES_TECHNICIAN")
        ok = self.wo(a, priority="CRITICAL", technician_id=t["id"])
        self.assertEqual(ok["status"], "ASSIGNED")

    def test_rule2_cannot_escalate_or_unassign_critical(self):
        a, t = self.asset(), self.tech()
        open_wo = self.wo(a)
        self.put(open_wo["id"], 422, priority="CRITICAL")                      # no technician
        self.put(open_wo["id"], priority="CRITICAL", technician_id=t["id"])    # both at once: fine
        crit = self.wo(a, priority="CRITICAL", technician_id=t["id"])
        self.put(crit["id"], 422, technician_id=None)                          # cannot unassign

    def test_rule3_completed_cannot_return_to_open(self):
        a, t = self.asset(), self.tech()
        wo = self.wo(a, technician_id=t["id"])
        self.put(wo["id"], status="IN_PROGRESS")
        done = self.put(wo["id"], status="COMPLETED")
        self.assertIsNotNone(done["completed_at"])
        err = self.put(wo["id"], 409, status="OPEN")["error"]
        self.assertEqual(err["code"], "INVALID_TRANSITION")
        for s in ("ASSIGNED", "IN_PROGRESS", "CANCELLED"):
            self.put(wo["id"], 409, status=s)
        self.put(wo["id"], 409, description="edit after completion")           # closed for edits too

    def test_rule4_cancelled_cannot_move_to_in_progress(self):
        a, t = self.asset(), self.tech()
        wo = self.wo(a, technician_id=t["id"])
        self.put(wo["id"], status="CANCELLED")
        err = self.put(wo["id"], 409, status="IN_PROGRESS")["error"]
        self.assertIn("cancelled", err["message"].lower())

    def test_rule5_schedule_not_in_past(self):
        a = self.asset()
        self.assertEqual(self.wo(a, expect=422, scheduled_date=PAST)["error"]["code"], "SCHEDULE_IN_PAST")
        self.wo(a, scheduled_date=TODAY.isoformat())                           # today is allowed
        wo = self.wo(a)
        self.put(wo["id"], 422, scheduled_date=PAST)                           # rescheduling into the past too
        self.put(wo["id"], scheduled_date="2026-12-01")

    def test_rule6_out_of_service_asset(self):
        a = self.asset(status="OUT_OF_SERVICE")
        err = self.wo(a, expect=422)["error"]
        self.assertEqual(err["code"], "ASSET_OUT_OF_SERVICE")
        emergency = self.wo(a, maintenance_type_code="EMERGENCY_REPAIR")
        self.assertTrue(emergency["maintenance_type"]["is_emergency"])
        # loophole: switching an emergency order to a normal type afterwards
        self.put(emergency["id"], 422, maintenance_type_code="REPAIR")
        # an asset that is back in service accepts normal work again
        self.c.put(f"/api/assets/{a['id']}", json={"status": "ACTIVE"})
        self.wo(a)

    def test_rule6_works_with_type_id(self):
        a = self.asset(status="OUT_OF_SERVICE")
        types = {t["code"]: t for t in self.c.get("/api/maintenance-types").get_json()}
        self.wo(a, expect=422, maintenance_type_code=None, maintenance_type_id=types["REPAIR"]["id"])
        self.wo(a, maintenance_type_code=None, maintenance_type_id=types["EMERGENCY_REPAIR"]["id"])


# ======================================================== state machine ====
class LifecycleTests(ApiTestCase):
    def test_happy_path_with_history(self):
        a, t = self.asset(), self.tech()
        wo = self.wo(a)
        self.assertEqual((wo["status"], wo["allowed_transitions"]), ("OPEN", ["ASSIGNED", "CANCELLED"]))
        wo = self.put(wo["id"], technician_id=t["id"])                         # assigning moves OPEN -> ASSIGNED
        self.assertEqual(wo["status"], "ASSIGNED")
        wo = self.put(wo["id"], status="IN_PROGRESS")
        wo = self.put(wo["id"], status="COMPLETED")
        self.assertEqual(wo["completed_at"], "2026-10-12T09:30:00Z")
        events = self.c.get(f"/api/work-orders/{wo['id']}/events").get_json()
        self.assertEqual([(e["event_type"], e["to_status"]) for e in events],
                         [("CREATED", "OPEN"), ("STATUS_CHANGED", "ASSIGNED"),
                          ("STATUS_CHANGED", "IN_PROGRESS"), ("STATUS_CHANGED", "COMPLETED")])

    def test_cannot_skip_states(self):
        a, t = self.asset(), self.tech()
        wo = self.wo(a)
        self.put(wo["id"], 409, status="IN_PROGRESS")
        self.put(wo["id"], 409, status="COMPLETED")
        assigned = self.wo(a, technician_id=t["id"])
        self.put(assigned["id"], 409, status="COMPLETED")

    def test_status_assigned_needs_technician(self):
        wo = self.wo(self.asset())
        self.assertEqual(self.put(wo["id"], 422, status="ASSIGNED")["error"]["code"], "TECHNICIAN_REQUIRED")

    def test_cancel_from_open_and_assigned_only(self):
        a, t = self.asset(), self.tech()
        self.assertEqual(self.put(self.wo(a)["id"], status="CANCELLED")["status"], "CANCELLED")
        self.assertEqual(self.put(self.wo(a, technician_id=t["id"])["id"], status="CANCELLED")["status"], "CANCELLED")
        started = self.wo(a, technician_id=t["id"])
        self.put(started["id"], status="IN_PROGRESS")
        self.put(started["id"], 409, status="CANCELLED")

    def test_technician_must_be_active_and_exist(self):
        a = self.asset()
        on_leave = self.tech(status="ON_LEAVE")
        self.assertEqual(self.wo(a, expect=422, technician_id=on_leave["id"])["error"]["code"], "TECHNICIAN_UNAVAILABLE")
        self.assertEqual(self.wo(a, expect=422, technician_id=999)["error"]["code"], "REFERENCE_NOT_FOUND")
        self.assertEqual(self.wo(a, expect=422, asset_id=999)["error"]["code"], "REFERENCE_NOT_FOUND")

    def test_reassign_until_in_progress(self):
        a, t1, t2 = self.asset(), self.tech(name="A"), self.tech(name="B")
        wo = self.wo(a, technician_id=t1["id"])
        wo = self.put(wo["id"], technician_id=t2["id"])
        self.assertEqual(wo["technician"]["name"], "B")
        self.put(wo["id"], status="IN_PROGRESS")
        self.put(wo["id"], 409, technician_id=t1["id"])

    def test_identity_fields_immutable_but_roundtrip_ok(self):
        a, b = self.asset(), self.asset()
        wo = self.wo(a)
        self.put(wo["id"], 422, asset_id=b["id"])
        self.put(wo["id"], 422, work_order_number="WO-HACK")
        same = self.put(wo["id"], asset_id=a["id"], work_order_number=wo["work_order_number"], description="x")
        self.assertEqual(same["description"], "x")

    def test_noop_update_creates_no_event(self):
        wo = self.wo(self.asset())
        self.put(wo["id"], description=wo["description"], priority=wo["priority"])
        self.assertEqual(len(self.c.get(f"/api/work-orders/{wo['id']}/events").get_json()), 1)

    def test_null_fields_rejected(self):
        wo = self.wo(self.asset())
        self.put(wo["id"], 422, priority=None)
        self.put(wo["id"], 422, status=None)


# ====================================================== search & history ===
class QueryTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.a1, self.a2 = self.asset(), self.asset()
        self.t1, self.t2 = self.tech(name="Asha"), self.tech(name="Ben")
        self.w_open = self.wo(self.a1, priority="LOW", description="Grease bearings")
        self.w_prog = self.wo(self.a1, priority="HIGH", technician_id=self.t1["id"], description="Replace seal")
        self.put(self.w_prog["id"], status="IN_PROGRESS")
        self.w_crit = self.wo(self.a2, priority="CRITICAL", technician_id=self.t2["id"],
                              maintenance_type_code="REPAIR", scheduled_date="2026-10-20")

    def numbers(self, qs):
        r = self.c.get(f"/api/work-orders?{qs}")
        self.assertEqual(r.status_code, 200, r.get_json())
        return {w["work_order_number"] for w in r.get_json()["items"]}

    def test_filters(self):
        self.assertEqual(self.numbers("status=IN_PROGRESS"), {self.w_prog["work_order_number"]})
        self.assertEqual(self.numbers("priority=HIGH"), {self.w_prog["work_order_number"]})
        self.assertEqual(self.numbers(f"asset_id={self.a2['id']}"), {self.w_crit["work_order_number"]})
        self.assertEqual(self.numbers(f"asset_code={self.a2['asset_id']}"), {self.w_crit["work_order_number"]})
        self.assertEqual(self.numbers(f"technician_id={self.t1['id']}"), {self.w_prog["work_order_number"]})
        self.assertEqual(self.numbers("maintenance_type=repair"), {self.w_crit["work_order_number"]})
        self.assertEqual(len(self.numbers("")), 3)

    def test_combined_and_multi_value_filters(self):
        self.assertEqual(self.numbers(f"asset_id={self.a1['id']}&status=OPEN"), {self.w_open["work_order_number"]})
        self.assertEqual(len(self.numbers("status=open,assigned")), 2)
        self.assertEqual(self.numbers(f"asset_id={self.a1['id']}&priority=CRITICAL"), set())
        self.assertEqual(self.numbers("scheduled_from=2026-10-15&scheduled_to=2026-10-25"),
                         {self.w_crit["work_order_number"]})

    def test_search(self):
        self.assertEqual(self.numbers("q=seal"), {self.w_prog["work_order_number"]})
        self.assertEqual(self.numbers(f"q={self.a2['asset_id']}"), {self.w_crit["work_order_number"]})
        self.assertEqual(self.numbers("q=Ben"), {self.w_crit["work_order_number"]})
        self.assertEqual(self.numbers("q=%25"), set())                         # LIKE wildcards are escaped

    def test_sorting_and_paging(self):
        r = self.c.get("/api/work-orders?sort=-priority").get_json()
        self.assertEqual([w["priority"] for w in r["items"]], ["CRITICAL", "HIGH", "LOW"])
        r = self.c.get("/api/work-orders?sort=scheduled_date&limit=2&offset=2").get_json()
        self.assertEqual((r["total"], len(r["items"])), (3, 1))

    def test_bad_filters_are_400(self):
        for qs in ("status=NOPE", "priority=URGENT", "asset_id=abc", "limit=0", "limit=9999",
                   "sort=colour", "scheduled_from=yesterday"):
            self.assertEqual(self.c.get(f"/api/work-orders?{qs}").status_code, 400, qs)

    def test_asset_history(self):
        self.put(self.w_prog["id"], status="COMPLETED")
        h = self.c.get(f"/api/assets/{self.a1['id']}/history").get_json()
        self.assertEqual(h["summary"]["total"], 2)
        self.assertEqual(h["summary"]["by_status"], {"OPEN": 1, "COMPLETED": 1})
        self.assertEqual(h["summary"]["last_completed_at"], "2026-10-12T09:30:00Z")
        done = self.c.get(f"/api/assets/{self.a1['id']}/history?status=COMPLETED").get_json()
        self.assertEqual(len(done["items"]), 1)
        self.assertEqual(self.c.get("/api/assets/999/history").status_code, 404)


# ================================================== database-level safety ===
class DatabaseConstraintTests(ApiTestCase):
    """The service layer is the first line of defence; these prove the schema is the second."""

    def insert(self, conn, **over):
        row = dict(work_order_number="WO-X", asset_id=1, maintenance_type_id=1, priority="LOW",
                   technician_id=None, scheduled_date="2026-11-01", status="OPEN", completed_at=None)
        row.update(over)
        conn.execute(
            "INSERT INTO work_orders (work_order_number, asset_id, maintenance_type_id, priority, technician_id,"
            " scheduled_date, status, completed_at, created_at, updated_at) VALUES"
            " (:work_order_number, :asset_id, :maintenance_type_id, :priority, :technician_id, :scheduled_date,"
            " :status, :completed_at, 't', 't')", row)

    def test_schema_rejects_invalid_rows(self):
        self.asset()
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        self.insert(conn)  # the baseline row is valid
        cases = {
            "rule 1: duplicate number": dict(work_order_number="wo-x"),
            "rule 2: CRITICAL without technician": dict(work_order_number="A", priority="CRITICAL"),
            "FK: unknown asset": dict(work_order_number="B", asset_id=999),
            "FK: unknown maintenance type": dict(work_order_number="C", maintenance_type_id=999),
            "ASSIGNED without technician": dict(work_order_number="D", status="ASSIGNED"),
            "unknown status value": dict(work_order_number="E", status="DONE"),
            "COMPLETED without completed_at": dict(work_order_number="F", status="COMPLETED", technician_id=1),
            "malformed date": dict(work_order_number="G", scheduled_date="12/10/2026"),
        }
        conn.execute("INSERT INTO technicians (name, skill, created_at, updated_at) VALUES ('T', 'S', 't', 't')")
        for label, over in cases.items():
            with self.subTest(label), self.assertRaises(sqlite3.IntegrityError):
                self.insert(conn, **over)
        with self.subTest("RESTRICT: cannot delete an asset that has history"), self.assertRaises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM assets WHERE id = 1")
        conn.close()


class ConcurrencyTests(ApiTestCase):
    """Writes use BEGIN IMMEDIATE, so read-modify-write sequences are serialised."""

    def run_parallel(self, fn, n):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=n) as pool:
            return list(pool.map(fn, range(n)))

    def test_parallel_creates_get_unique_numbers(self):
        a = self.asset()
        body = self.wo_body(a)

        def create(_):
            r = self.app.test_client().post("/api/work-orders", json=body)
            return r.status_code, r.get_json().get("work_order_number")

        results = self.run_parallel(create, 12)
        self.assertTrue(all(code == 201 for code, _ in results), results)
        self.assertEqual(len({num for _, num in results}), 12)

    def test_competing_transitions_exactly_one_wins(self):
        a, t = self.asset(), self.tech()
        for _ in range(5):
            wo = self.wo(a, technician_id=t["id"])          # ASSIGNED

            def move(i):
                target = "IN_PROGRESS" if i % 2 == 0 else "CANCELLED"
                return self.app.test_client().put(f"/api/work-orders/{wo['id']}", json={"status": target}).status_code

            codes = sorted(self.run_parallel(move, 6))
            self.assertEqual(set(codes), {200, 409}, codes)   # the loser(s) are rejected, never both applied
            final = self.c.get(f"/api/work-orders/{wo['id']}").get_json()["status"]
            events = self.c.get(f"/api/work-orders/{wo['id']}/events").get_json()
            self.assertIn(final, ("IN_PROGRESS", "CANCELLED"))
            self.assertEqual(len(events), 2)                  # CREATED + exactly one status change


if __name__ == "__main__":
    unittest.main()
