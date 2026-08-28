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
    CurrentItemPrice,
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

# Labor API models
from app.models.labor import (
    DailyLog,
    PayGroups,
    WeeklyLaborEntry,
    SalesByDesignation,
    FilmUsage,
    SalesRecord,
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

# Anomaly detection models
from app.models.anomalies import (
    EntityStat,
    Anomaly,
    JobRun,
)

# Analytics models
from app.models.analytics import AnalyticsFact

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
    "CurrentItemPrice",
    "PriceHistory",
    "PriceSheet",
    "PriceSheetBackup",
    "price_sheet_items",
    "price_sheet_backup_items",
    # Costing
    "LaborCost",
    "CostHistory",
    # Labor API
    "DailyLog",
    "PayGroups",
    "WeeklyLaborEntry",
    "SalesByItemType",
    "FilmUsage",
    "SalesRecord",
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
    # Anomalies
    "EntityStat",
    "Anomaly",
    "JobRun",
    # Analytics
    "AnalyticsFact",
]
