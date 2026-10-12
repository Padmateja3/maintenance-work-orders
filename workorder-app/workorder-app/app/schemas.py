"""Request validation (pydantic). Enum-like values are case-insensitive."""
from datetime import date
from typing import Annotated, ClassVar, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def _upper(v):
    return v.strip().upper() if isinstance(v, str) else v


Upper = BeforeValidator(_upper)
AssetStatus = Annotated[Literal["ACTIVE", "INACTIVE", "OUT_OF_SERVICE"], Upper]
TechnicianStatus = Annotated[Literal["ACTIVE", "INACTIVE", "ON_LEAVE"], Upper]
Priority = Annotated[Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"], Upper]
WorkOrderStatus = Annotated[Literal["OPEN", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"], Upper]

Short = Annotated[str, Field(min_length=1, max_length=120)]


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class _Patch(_Base):
    """For PUT bodies: only the fields sent are changed; explicit null is
    rejected unless the field is listed in `nullable`."""

    nullable: ClassVar[set[str]] = set()

    @model_validator(mode="after")
    def _no_nulls(self):
        for name in self.model_fields_set:
            if name not in self.nullable and getattr(self, name) is None:
                raise ValueError(f"{name} may not be null")
        return self


# ---- assets ---------------------------------------------------------------
class AssetCreate(_Base):
    asset_id: Annotated[str, Field(min_length=1, max_length=50)]
    asset_type: Short
    manufacturer: Short
    model: Short
    serial_number: Short
    usage_hours: Annotated[float, Field(ge=0)] = 0
    usage_cycles: Annotated[int, Field(ge=0)] = 0
    status: AssetStatus = "ACTIVE"


class AssetUpdate(_Patch):
    asset_id: Optional[Annotated[str, Field(min_length=1, max_length=50)]] = None
    asset_type: Optional[Short] = None
    manufacturer: Optional[Short] = None
    model: Optional[Short] = None
    serial_number: Optional[Short] = None
    usage_hours: Optional[Annotated[float, Field(ge=0)]] = None
    usage_cycles: Optional[Annotated[int, Field(ge=0)]] = None
    status: Optional[AssetStatus] = None


# ---- technicians ----------------------------------------------------------
class TechnicianCreate(_Base):
    name: Short
    skill: Short
    status: TechnicianStatus = "ACTIVE"


class TechnicianUpdate(_Patch):
    name: Optional[Short] = None
    skill: Optional[Short] = None
    status: Optional[TechnicianStatus] = None


# ---- work orders ----------------------------------------------------------
class _TypeRef(BaseModel):
    @model_validator(mode="after")
    def _type_ref(self):
        if self.maintenance_type_id is not None and self.maintenance_type_code is not None:
            raise ValueError("send either maintenance_type_id or maintenance_type_code, not both")
        return self


class WorkOrderCreate(_TypeRef, _Base):
    work_order_number: Optional[Annotated[str, Field(min_length=1, max_length=40)]] = None  # generated if omitted
    asset_id: int  # internal id of the asset
    maintenance_type_id: Optional[int] = None
    maintenance_type_code: Optional[Annotated[str, Upper, Field(min_length=1, max_length=40)]] = None
    description: Annotated[str, Field(max_length=2000)] = ""
    priority: Priority
    technician_id: Optional[int] = None
    scheduled_date: date

    @model_validator(mode="after")
    def _need_type(self):
        if self.maintenance_type_id is None and self.maintenance_type_code is None:
            raise ValueError("maintenance_type_id or maintenance_type_code is required")
        return self


class WorkOrderUpdate(_TypeRef, _Patch):
    nullable: ClassVar[set[str]] = {"technician_id"}

    # Identity fields: accepted only so a client can round-trip a full object;
    # a different value is rejected by the service (they are immutable).
    work_order_number: Optional[str] = None
    asset_id: Optional[int] = None

    maintenance_type_id: Optional[int] = None
    maintenance_type_code: Optional[Annotated[str, Upper, Field(min_length=1, max_length=40)]] = None
    description: Optional[Annotated[str, Field(max_length=2000)]] = None
    priority: Optional[Priority] = None
    technician_id: Optional[int] = None
    scheduled_date: Optional[date] = None
    status: Optional[WorkOrderStatus] = None
