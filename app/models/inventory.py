# Copyright Cade Stocker 2026
"""Inventory and product-related models."""

from app import db
from datetime import datetime
from app.models.core import UnitOfWeight, ItemDesignation


# Association table for Item ↔ RawProduct
item_raw = db.Table('item_raw',
    db.Column('item_id', db.Integer, db.ForeignKey('item.id'), primary_key=True),
    db.Column('raw_product_id', db.Integer, db.ForeignKey('raw_product.id'), primary_key=True)
)


class RawProduct(db.Model):
    """Raw materials used in production."""
    __tablename__ = 'raw_product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    lot_code = db.Column(db.String(100))
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, name, company_id, lot_code=None):
        self.name = name
        self.company_id = company_id
        self.lot_code = lot_code

    def __repr__(self):
        return f"RawProduct('{self.name}', '{self.lot_code}')"


class Item(db.Model):
    """Finished goods items sold to customers."""
    __tablename__ = 'item'
    raw_products = db.relationship('RawProduct', secondary=item_raw, backref=db.backref('items', lazy='dynamic'))
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(100), nullable=False)
    unit_of_weight = db.Column(db.Enum(UnitOfWeight), nullable=False)
    alternate_code = db.Column(db.String(100), nullable=True)
    ranch = db.Column(db.Boolean, nullable=False, default=False)
    case_weight = db.Column(db.Float, nullable=False, default=0.0)
    packaging_id = db.Column(db.Integer, db.ForeignKey('packaging.id'), nullable=False)
    item_designation = db.Column(db.Enum(ItemDesignation), nullable=False, default=ItemDesignation.FOODSERVICE)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, name, code, unit_of_weight, packaging_id, company_id, case_weight=0.0, ranch=False, item_designation=ItemDesignation.FOODSERVICE, raw_product_ids=None, alternate_code=None):
        self.name = name
        self.code = code
        self.unit_of_weight = unit_of_weight
        self.item_designation = item_designation
        self.packaging_id = packaging_id
        self.case_weight = case_weight
        self.ranch = ranch
        self.company_id = company_id
        self.alternate_code = alternate_code

    def __repr__(self):
        return f"Item('{self.name}', '{self.alternate_code}', '{self.code}', '{self.unit_of_weight}', '{self.case_weight}', '{self.packaging_id}', '{self.item_designation}')"


class ItemInfo(db.Model):
    """Product information for items (yield, labor hours, etc.)."""
    __tablename__ = 'item_info'
    id = db.Column(db.Integer, primary_key=True)
    product_yield = db.Column(db.Float, nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    labor_hours = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, product_yield, item_id, labor_hours, date, company_id):
        self.product_yield = product_yield
        self.item_id = item_id
        self.labor_hours = labor_hours
        self.date = date
        self.company_id = company_id

    def __repr__(self):
        return f"ItemInfo('{self.product_yield}', '{self.labor_hours}', '{self.date}', '{self.company_id}')"


class ItemTotalCost(db.Model):
    """Total cost breakdown for items on a given date."""
    __tablename__ = 'item_total_cost'
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    ranch_cost = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    packaging_cost = db.Column(db.Float, nullable=False)
    raw_product_cost = db.Column(db.Float, nullable=False)
    labor_cost = db.Column(db.Float, nullable=False)
    designation_cost = db.Column(db.Float, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, item_id, date, total_cost, ranch_cost, packaging_cost, raw_product_cost, labor_cost, designation_cost, company_id):
        self.item_id = item_id
        self.date = date
        self.total_cost = total_cost
        self.ranch_cost = ranch_cost
        self.packaging_cost = packaging_cost
        self.raw_product_cost = raw_product_cost
        self.labor_cost = labor_cost
        self.designation_cost = designation_cost
        self.company_id = company_id

    def __repr__(self):
        return f"ItemTotalCost('{self.item_id}', '{self.date}', '{self.total_cost}', '{self.packaging_cost}', '{self.raw_product_cost}', '{self.labor_cost}', '{self.designation_cost}')"


class InventorySession(db.Model):
    """An inventory-taking event."""
    __tablename__ = 'inventory_session'
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(200), nullable=True)
    counted_by = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.String(500), nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    item_counts = db.relationship(
        'ItemInventory', backref='session', lazy=True, cascade='all, delete-orphan'
    )
    supply_counts = db.relationship(
        'SupplyInventory', backref='session', lazy=True, cascade='all, delete-orphan'
    )

    def __init__(self, company_id, counted_by=None, label=None, notes=None, submitted_at=None):
        self.company_id = company_id
        self.counted_by = counted_by
        self.label = label
        self.notes = notes
        if submitted_at:
            self.submitted_at = submitted_at

    def __repr__(self):
        return f"InventorySession(id={self.id}, label='{self.label}', submitted={self.submitted_at})"


class ItemInventory(db.Model):
    """Inventory count line item for finished goods."""
    __tablename__ = 'inventory_count'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey('inventory_session.id'), nullable=True, index=True
    )
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    count_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    counted_by = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.String(500), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    item = db.relationship('Item', backref='inventory_counts')

    def __init__(self, item_id, quantity, company_id, session_id=None,
                 count_date=None, counted_by=None, notes=None):
        self.item_id = item_id
        self.quantity = quantity
        self.company_id = company_id
        self.session_id = session_id
        self.counted_by = counted_by
        self.notes = notes
        if count_date:
            self.count_date = count_date

    def __repr__(self):
        return f"ItemInventory(item_id={self.item_id}, quantity={self.quantity}, date={self.count_date})"


class Supply(db.Model):
    """Catalog of supplies (boxes, bags, etc.)."""
    __tablename__ = 'supply'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    unit = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    inventory_counts = db.relationship('SupplyInventory', backref='supply', lazy=True,
                                       cascade='all, delete-orphan')

    def __init__(self, name, unit, company_id, category=None, notes=None, is_active=True):
        self.name = name
        self.unit = unit
        self.company_id = company_id
        self.category = category
        self.notes = notes
        self.is_active = is_active

    def __repr__(self):
        return f"Supply('{self.name}', unit='{self.unit}', category='{self.category}')"


class SupplyInventory(db.Model):
    """Inventory count line item for supplies."""
    __tablename__ = 'supply_inventory_count'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey('inventory_session.id'), nullable=True, index=True
    )
    supply_id = db.Column(db.Integer, db.ForeignKey('supply.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    count_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    counted_by = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.String(500), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, supply_id, quantity, company_id, session_id=None,
                 count_date=None, counted_by=None, notes=None):
        self.supply_id = supply_id
        self.quantity = quantity
        self.company_id = company_id
        self.session_id = session_id
        self.counted_by = counted_by
        self.notes = notes
        if count_date:
            self.count_date = count_date

    def __repr__(self):
        return f"SupplyInventory(supply_id={self.supply_id}, quantity={self.quantity}, date={self.count_date})"
