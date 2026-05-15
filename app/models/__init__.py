# Copyright Cade Stocker 2026
"""
Database models for the application.

This package organizes models by domain:
- auth: Authentication and user management
- inventory: Raw products and finished goods inventory
- pricing: Price sheets and pricing data
- costing: Cost tracking and labor costs
- customers: Customer information
- suppliers: Suppliers and growers
- receiving: Receiving logs and images
- core: Core enums, shared models, and utilities
"""

# Database instance
from app import db

# Core enums and classes
from app.models.core import (
    UnitOfWeight,
    ItemDesignation,
    AIResponse,
    Packaging,
    PackagingCost,
    EmailTemplate,
)

# Auth models
from app.models.auth import (
    Company,
    User,
    Notification,
    PendingUser,
    APIKey,
    load_user,
)

# Inventory models
from app.models.inventory import (
    RawProduct,
    Item,
    ItemInfo,
    ItemTotalCost,
    InventorySession,
    ItemInventory,
    Supply,
    SupplyInventory,
    item_raw,
)

# Pricing models
from app.models.pricing import (
    DesignationCost,
    RanchPrice,
    PriceHistory,
    PriceSheet,
    PriceSheetBackup,
    price_sheet_items,
    price_sheet_backup_items,
)

# Costing models
from app.models.costing import (
    LaborCost,
    CostHistory,
)

# Customer models
from app.models.customers import (
    Customer,
    CustomerEmail,
)

# Supplier models
from app.models.suppliers import (
    BrandName,
    Seller,
    GrowerOrDistributor,
)

# Receiving models
from app.models.receiving import (
    ReceivingLog,
    ReceivingImage,
)

__all__ = [
    # Database
    "db",
    # Core
    "UnitOfWeight",
    "ItemDesignation",
    "AIResponse",
    "Packaging",
    "PackagingCost",
    "EmailTemplate",
    # Auth
    "Company",
    "User",
    "Notification",
    "PendingUser",
    "APIKey",
    "load_user",
    # Inventory
    "RawProduct",
    "Item",
    "ItemInfo",
    "ItemTotalCost",
    "InventorySession",
    "ItemInventory",
    "Supply",
    "SupplyInventory",
    "item_raw",
    # Pricing
    "DesignationCost",
    "RanchPrice",
    "PriceHistory",
    "PriceSheet",
    "PriceSheetBackup",
    "price_sheet_items",
    "price_sheet_backup_items",
    # Costing
    "LaborCost",
    "CostHistory",
    # Customers
    "Customer",
    "CustomerEmail",
    # Suppliers
    "BrandName",
    "Seller",
    "GrowerOrDistributor",
    # Receiving
    "ReceivingLog",
    "ReceivingImage",
]
