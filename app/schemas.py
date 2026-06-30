# Copyright Cade Stocker 2026

"""
Input validation schemas for API endpoints using Pydantic.
    Pydantic models define the expected structure and types of incoming JSON data for each API endpoint.

Provides type safety and input sanitization for all API requests.

API is used for things like - creating receiving logs, submitting inventory counts, and managing the supply catalog.

So this file essentially defines the "contracts" for what data the frontend must send to the backend for these operations,
and ensures that the data is valid and safe to process.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime as dt_type, date as date_type

# bleach is an optional dependency for sanitizing text fields to prevent XSS attacks.
# If it's not available, fall back to basic HTML escaping.
try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False
    import html


class ReceivingLogCreateSchema(BaseModel):
    """Schema for creating a receiving log with strict validation."""
    
    model_config = ConfigDict(strict=False)
    
    # Required fields with type validation
    raw_product_id: int = Field(..., gt=0, description="ID must be a positive integer")
    pack_size_unit: str = Field(..., min_length=1, max_length=50)
    pack_size: float = Field(..., gt=0)
    brand_name_id: int = Field(..., gt=0)
    quantity_received: int = Field(..., ge=0)
    seller_id: int = Field(..., gt=0)
    temperature: Optional[float] = None
    hold_or_used: str = Field(..., pattern='^(hold|used)$')
    grower_or_distributor_id: int = Field(..., gt=0)
    country_of_origin: str = Field(..., min_length=1, max_length=100)
    received_by: Optional[str] = Field(None, max_length=200)
    returned: Optional[str] = Field(None, max_length=500)
    datetime: Optional[dt_type] = None
    price_paid: Optional[float] = Field(None, ge=0, description="Price paid per unit (optional)")
    
    @field_validator('pack_size_unit', 'country_of_origin', 'received_by', 'returned')
    @classmethod
    def sanitize_text_fields(cls, v: Optional[str]) -> Optional[str]:
        
        """
        Sanitize text fields to prevent XSS attacks.
        """

        if v is None:
            return v
        # Remove any HTML/script tags
        if BLEACH_AVAILABLE:
            sanitized = bleach.clean(v, tags=[], strip=True)
        else:
            # Fallback: escape HTML entities
            sanitized = html.escape(v)
        return sanitized
    
    @field_validator('hold_or_used')
    @classmethod
    def validate_hold_or_used(cls, v: str) -> str:
        """Ensure hold_or_used is only 'hold' or 'used'."""
        if v not in ['hold', 'used']:
            raise ValueError("hold_or_used must be either 'hold' or 'used'")
        return v


class ItemInventoryCreateSchema(BaseModel):
    """Schema for submitting a finished-goods inventory count from the iPad."""

    model_config = ConfigDict(strict=False)

    item_id: int = Field(..., gt=0)
    quantity: int = Field(..., ge=0)
    counted_by: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=500)
    count_date: Optional[dt_type] = None

    @field_validator('counted_by', 'notes')
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if BLEACH_AVAILABLE:
            return bleach.clean(v, tags=[], strip=True)
        return html.escape(v)


class SupplyCreateSchema(BaseModel):
    """Schema for creating a new supply catalog entry."""

    model_config = ConfigDict(strict=False)

    name: str = Field(..., min_length=1, max_length=100)
    unit: str = Field(..., min_length=1, max_length=50)
    category: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=500)
    is_active: bool = True

    @field_validator('name', 'unit', 'category', 'notes')
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if BLEACH_AVAILABLE:
            return bleach.clean(v, tags=[], strip=True)
        return html.escape(v)


class SupplyInventoryCreateSchema(BaseModel):
    """Schema for submitting a supply inventory count from the iPad."""

    model_config = ConfigDict(strict=False)

    supply_id: int = Field(..., gt=0)
    quantity: float = Field(..., ge=0)
    counted_by: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=500)
    count_date: Optional[dt_type] = None

    @field_validator('counted_by', 'notes')
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if BLEACH_AVAILABLE:
            return bleach.clean(v, tags=[], strip=True)
        return html.escape(v)


class DailyLogCreateSchema(BaseModel):
    """Schema for creating a daily labor log."""

    model_config = ConfigDict(strict=False)

    date: Optional[date_type] = None
    items: int = Field(..., ge=0)
    sales: float = Field(..., ge=0)
    labor_hours: float = Field(..., ge=0)
    overtime_hours: float = Field(..., ge=0)
    payroll_cost: float = Field(..., ge=0)
    number_of_employees: int = Field(..., ge=0)
    labor_ratio: float
    sales_over_labor_cost: float
    average_man_hour_cost: float
    average_case_cost: float
    average_hours_per_employee: float


class PayGroupCreateSchema(BaseModel):
    """Schema for creating a pay group."""

    model_config = ConfigDict(strict=False)

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=255)

    @field_validator('name', 'description')
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if BLEACH_AVAILABLE:
            return bleach.clean(v, tags=[], strip=True)
        return html.escape(v)


class WeeklyLaborEntryCreateSchema(BaseModel):
    """Schema for creating a weekly labor summary entry."""

    model_config = ConfigDict(strict=False)

    week_start_date: date_type
    pay_group_id: int = Field(..., gt=0)
    regular_hours: float = Field(..., ge=0)
    overtime_hours: float = Field(..., ge=0)
    pay: float = Field(..., ge=0)
    percent_of_sales: float
    cost_per_hour: float = Field(..., ge=0)
    number_in_pay_group: int = Field(..., ge=0)
    number_with_overtime: int = Field(..., ge=0)
    average_hours_per_employee: float = Field(..., ge=0)


class SalesByItemTypeCreateSchema(BaseModel):
    """Schema for creating sales by item type."""

    model_config = ConfigDict(strict=False)

    date: date_type
    item_type_id: int = Field(..., gt=0)
    number_of_items: int = Field(..., ge=0)
    sales: float = Field(..., ge=0)
    average_price_per_item: float = Field(..., ge=0)
    percent_of_total_sales: float
    percent_of_total_boxes: float


class FilmUsageCreateSchema(BaseModel):
    """Schema for creating monthly film usage counts."""

    model_config = ConfigDict(strict=False)

    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2000)
    number_of_cases: int = Field(..., ge=0)
    number_of_rolls: int = Field(..., ge=0)


def validate_foreign_key_exists(model_class, field_id: int, company_id: int, field_name: str):
    """
    Validate that a foreign key exists and belongs to the user's company.
    
    Args:
        model_class: The SQLAlchemy model class to query
        field_id: The ID to validate
        company_id: The company ID to filter by
        field_name: Name of the field (for error messages)
    
    Returns:
        The model instance if found
    
    Raises:
        ValueError: If the ID doesn't exist or doesn't belong to the company
    """
    instance = model_class.query.filter_by(
        id=field_id,
        company_id=company_id
    ).first()
    
    if not instance:
        raise ValueError(f"Invalid {field_name}: ID {field_id} not found or not accessible")
    
    return instance


# ---------------------------------------------------------------------------
# Inventory session schemas
# ---------------------------------------------------------------------------

class ItemInventoryLineSchema(BaseModel):
    """One finished-goods line inside an inventory session submission."""

    model_config = ConfigDict(strict=False)

    item_id: int = Field(..., gt=0)
    quantity: int = Field(..., ge=0)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator('notes')
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if BLEACH_AVAILABLE:
            return bleach.clean(v, tags=[], strip=True)
        return html.escape(v)


class SupplyInventoryLineSchema(BaseModel):
    """One supply line inside an inventory session submission."""

    model_config = ConfigDict(strict=False)

    supply_id: int = Field(..., gt=0)
    quantity: float = Field(..., ge=0)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator('notes')
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if BLEACH_AVAILABLE:
            return bleach.clean(v, tags=[], strip=True)
        return html.escape(v)


class InventorySessionCreateSchema(BaseModel):
    """Full inventory session submitted in one JSON payload from the iPad.

    Example payload::

        {
            "label": "Morning count",
            "counted_by": "John",
            "notes": "Cooler #2 was locked",
            "submitted_at": "2026-03-06T08:00:00",   // optional
            "item_counts": [
                {"item_id": 1, "quantity": 40},
                {"item_id": 3, "quantity": 12, "notes": "One damaged box"}
            ],
            "supply_counts": [
                {"supply_id": 2, "quantity": 5},
                {"supply_id": 4, "quantity": 0.5, "notes": "Half roll left"}
            ]
        }
    """

    model_config = ConfigDict(strict=False)

    label: Optional[str] = Field(None, max_length=200)
    counted_by: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=500)
    submitted_at: Optional[dt_type] = None
    item_counts: List[ItemInventoryLineSchema] = Field(default_factory=list)
    supply_counts: List[SupplyInventoryLineSchema] = Field(default_factory=list)

    @field_validator('label', 'counted_by', 'notes')
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if BLEACH_AVAILABLE:
            return bleach.clean(v, tags=[], strip=True)
        return html.escape(v)
