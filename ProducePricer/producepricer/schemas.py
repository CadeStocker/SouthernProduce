"""
Input validation schemas for API endpoints using Pydantic.
Provides type safety and input sanitization for all API requests.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
from datetime import datetime as dt_type
try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False
    import html


class ReceivingLogCreateSchema(BaseModel):
    """Schema for creating a receiving log with strict validation."""
    
    model_config = ConfigDict(strict=True)
    
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
