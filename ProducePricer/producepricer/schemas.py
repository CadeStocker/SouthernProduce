"""
Input validation schemas for API endpoints using Pydantic.
Provides type safety and input sanitization for all API requests.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime as dt_type
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
        """Sanitize text fields to prevent XSS attacks."""
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
