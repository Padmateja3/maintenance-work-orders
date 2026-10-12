"""Unit tests for the pure business rules (no Flask, no DB)."""
import itertools
import unittest
from datetime import date

from app import rules
from app.rules import RuleViolation

VALID = {
    ("OPEN", "ASSIGNED"), ("OPEN", "CANCELLED"),
    ("ASSIGNED", "IN_PROGRESS"), ("ASSIGNED", "CANCELLED"),
    ("IN_PROGRESS", "COMPLETED"),
}


class TransitionTests(unittest.TestCase):
    def test_exhaustive_matrix(self):
        """Every (from, to) pair either is in VALID or raises a 409."""
        for cur, target in itertools.product(rules.STATUSES, rules.STATUSES):
            if cur == target:
                rules.check_transition(cur, target)  # no-op is allowed
            elif (cur, target) in VALID:
                rules.check_transition(cur, target)
            else:
                with self.assertRaises(RuleViolation, msg=f"{cur}->{target}") as ctx:
                    rules.check_transition(cur, target)
                self.assertEqual(ctx.exception.status, 409)

    def test_rule3_completed_cannot_reopen(self):
        with self.assertRaisesRegex(RuleViolation, "cannot be reopened"):
            rules.check_transition("COMPLETED", "OPEN")

    def test_rule4_cancelled_cannot_start(self):
        with self.assertRaisesRegex(RuleViolation, "cancelled work order cannot be moved to IN_PROGRESS"):
            rules.check_transition("CANCELLED", "IN_PROGRESS")

    def test_terminal_states_have_no_exits(self):
        self.assertEqual(rules.allowed_transitions("COMPLETED"), ())
        self.assertEqual(rules.allowed_transitions("CANCELLED"), ())


class OtherRuleTests(unittest.TestCase):
    def test_rule2(self):
        rules.check_critical_has_technician("CRITICAL", 7)
        rules.check_critical_has_technician("HIGH", None)
        with self.assertRaises(RuleViolation):
            rules.check_critical_has_technician("CRITICAL", None)

    def test_rule5(self):
        today = date(2026, 10, 12)
        rules.check_schedule_not_in_past(today, today)
        rules.check_schedule_not_in_past(date(2026, 10, 13), today)
        with self.assertRaises(RuleViolation):
            rules.check_schedule_not_in_past(date(2026, 10, 11), today)

    def test_rule6(self):
        rules.check_asset_accepts_maintenance("ACTIVE", False)
        rules.check_asset_accepts_maintenance("INACTIVE", False)
        rules.check_asset_accepts_maintenance("OUT_OF_SERVICE", True)
        with self.assertRaises(RuleViolation):
            rules.check_asset_accepts_maintenance("OUT_OF_SERVICE", False)


if __name__ == "__main__":
    unittest.main()
