"""Time helpers.

Business rule 5 depends on "today", so the clock is injectable via app config
(NOW_FN / TODAY_FN). Tests use this to stay deterministic.
"""
from datetime import date, datetime, timezone

from flask import current_app


def now() -> datetime:
    fn = current_app.config.get("NOW_FN")
    return fn() if fn else datetime.now(timezone.utc)


def today() -> date:
    fn = current_app.config.get("TODAY_FN")
    return fn() if fn else date.today()


def now_iso() -> str:
    return now().strftime("%Y-%m-%dT%H:%M:%SZ")
