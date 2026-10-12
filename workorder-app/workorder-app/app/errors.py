"""Uniform JSON errors:  {"error": {"code": ..., "message": ..., "details": [...]}}"""
import sqlite3

from flask import jsonify, request
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

from .rules import RuleViolation


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


# Friendly messages when a database constraint is what catches the problem
# (this also covers races between two concurrent requests).
UNIQUE_MESSAGES = {
    "work_orders.work_order_number": ("DUPLICATE_WORK_ORDER_NUMBER", "A work order with this number already exists."),
    "assets.asset_id": ("DUPLICATE_ASSET_ID", "An asset with this Asset ID already exists."),
    "assets.manufacturer": ("DUPLICATE_SERIAL_NUMBER", "An asset with this manufacturer and serial number already exists."),
}


def _body(status, code, message, details=None):
    err = {"code": code, "message": message}
    if details:
        err["details"] = details
    return jsonify({"error": err}), status


def register(app) -> None:
    @app.errorhandler(ApiError)
    def _api_error(e):
        return _body(e.status, e.code, e.message, e.details)

    @app.errorhandler(RuleViolation)
    def _rule(e):
        details = [{"field": e.field, "message": e.message}] if e.field else None
        return _body(e.status, e.code, e.message, details)

    @app.errorhandler(ValidationError)
    def _validation(e):
        details = []
        for err in e.errors():
            msg = err["msg"].removeprefix("Value error, ")
            details.append({"field": ".".join(str(p) for p in err["loc"]), "message": msg})
        return _body(422, "VALIDATION_ERROR", "The request body is invalid.", details)

    @app.errorhandler(sqlite3.IntegrityError)
    def _integrity(e):
        text = str(e)
        if "UNIQUE constraint failed" in text:
            for needle, (code, message) in UNIQUE_MESSAGES.items():
                if needle in text:
                    return _body(409, code, message)
            return _body(409, "DUPLICATE", "A record with these values already exists.")
        return _body(409, "CONSTRAINT_VIOLATION", f"The change violates a data constraint ({text}).")

    @app.errorhandler(HTTPException)
    def _http(e):
        if request.path.startswith("/api"):
            return _body(e.code, e.name.upper().replace(" ", "_"), e.description)
        return e
