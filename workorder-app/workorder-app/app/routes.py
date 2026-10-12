"""HTTP layer: parse, call a service, return JSON. No business logic here."""
from flask import Blueprint, jsonify, request

from . import schemas, services
from .db import get_db
from .errors import ApiError

bp = Blueprint("api", __name__, url_prefix="/api")


def _parse(model):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "INVALID_JSON", "The request body must be a JSON object.")
    return model.model_validate(data)


# ---- assets -----------------------------------------------------------------
@bp.post("/assets")
def create_asset():
    return jsonify(services.create_asset(get_db(), _parse(schemas.AssetCreate))), 201


@bp.get("/assets")
def list_assets():
    return jsonify(services.list_assets(get_db(), request.args))


@bp.get("/assets/<int:pk>")
def get_asset(pk):
    return jsonify(services.get_asset(get_db(), pk))


@bp.put("/assets/<int:pk>")
def update_asset(pk):
    return jsonify(services.update_asset(get_db(), pk, _parse(schemas.AssetUpdate)))


@bp.get("/assets/<int:pk>/history")
def asset_history(pk):
    return jsonify(services.asset_history(get_db(), pk, request.args))


# ---- technicians ----------------------------------------------------------------
@bp.post("/technicians")
def create_technician():
    return jsonify(services.create_technician(get_db(), _parse(schemas.TechnicianCreate))), 201


@bp.get("/technicians")
def list_technicians():
    return jsonify(services.list_technicians(get_db(), request.args))


@bp.get("/technicians/<int:pk>")
def get_technician(pk):
    return jsonify(services.get_technician(get_db(), pk))


@bp.put("/technicians/<int:pk>")
def update_technician(pk):
    return jsonify(services.update_technician(get_db(), pk, _parse(schemas.TechnicianUpdate)))


# ---- maintenance types ----------------------------------------------------------
@bp.get("/maintenance-types")
def list_maintenance_types():
    return jsonify(services.list_maintenance_types(get_db()))


# ---- work orders ---------------------------------------------------------------
@bp.post("/work-orders")
def create_work_order():
    return jsonify(services.create_work_order(get_db(), _parse(schemas.WorkOrderCreate))), 201


@bp.get("/work-orders")
def list_work_orders():
    return jsonify(services.list_work_orders(get_db(), request.args))


@bp.get("/work-orders/<int:pk>")
def get_work_order(pk):
    return jsonify(services.get_work_order(get_db(), pk))


@bp.put("/work-orders/<int:pk>")
def update_work_order(pk):
    return jsonify(services.update_work_order(get_db(), pk, _parse(schemas.WorkOrderUpdate)))


@bp.get("/work-orders/<int:pk>/events")
def work_order_events(pk):
    return jsonify(services.list_events(get_db(), pk))
