# Copyright Cade Stocker 2026
"""Pricing and cost-related models."""

from app import db
from datetime import datetime
from app.models.core import ItemDesignation


# Association table for PriceSheet ↔ Item
price_sheet_items = db.Table(
    'price_sheet_items',
    db.Column('price_sheet_id', db.Integer, db.ForeignKey('price_sheet.id'), primary_key=True),
    db.Column('item_id',         db.Integer, db.ForeignKey('item.id'),        primary_key=True)
)

# Association table for PriceSheetBackup ↔ Item
price_sheet_backup_items = db.Table(
    'price_sheet_backup_items',
    db.Column('price_sheet_backup_id', db.Integer, db.ForeignKey('price_sheet_backup.id'), primary_key=True),
    db.Column('item_id',               db.Integer, db.ForeignKey('item.id'),              primary_key=True)
)


class DesignationCost(db.Model):
    """Cost based on item designation."""
    __tablename__ = 'designation_cost'
    id = db.Column(db.Integer, primary_key=True)
    item_designation = db.Column(db.Enum(ItemDesignation), nullable=False)
    cost = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, item_designation, cost, date, company_id):
        self.item_designation = item_designation
        self.cost = cost
        self.date = date
        self.company_id = company_id

    def __repr__(self):
        return f"DesignationCost('{self.item_designation}', '{self.cost}', '{self.date}')"


class RanchPrice(db.Model):
    """Ranch product pricing information."""
    __tablename__ = 'ranch_price'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, date, cost, price, company_id):
        self.date = date
        self.cost = cost
        self.price = price
        self.company_id = company_id

    def __repr__(self):
        return f"RanchPrice('{self.date}', '{self.price}')"


class PriceHistory(db.Model):
    """Historical pricing for items per customer."""
    __tablename__ = 'price_history'
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    
    def __init__(self, item_id, date, company_id, customer_id, price):
        self.item_id = item_id
        self.date = date
        self.company_id = company_id
        self.customer_id = customer_id
        self.price = price

    def __repr__(self):
        return f"PriceHistory('{self.item_id}', '{self.date}', '{self.company_id}', '{self.customer_id}', '{self.price}')"


class PriceSheet(db.Model):
    """Price sheet for a customer."""
    __tablename__ = 'price_sheet'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    valid_from = db.Column(db.Date, nullable=True)
    valid_to = db.Column(db.Date, nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)

    items = db.relationship('Item', 
        secondary=price_sheet_items,
        backref=db.backref('price_sheets', lazy='dynamic'),
        lazy='subquery'
    )

    def __init__(self, name, date, company_id, customer_id, valid_from=None, valid_to=None):
        self.name = name
        self.date = date
        self.valid_from = valid_from if valid_from else date
        self.valid_to = valid_to
        self.company_id = company_id
        self.customer_id = customer_id

    def __repr__(self):
        if self.valid_from and self.valid_to:
            return f"PriceSheet('{self.name}', valid: {self.valid_from} to {self.valid_to})"
        return f"PriceSheet('{self.name}', '{self.date}')"
    
    def is_valid_on_date(self, check_date):
        """Check if this price sheet is valid on a given date."""
        if not self.valid_from:
            return self.date == check_date
        
        if self.valid_to:
            return self.valid_from <= check_date <= self.valid_to
        else:
            return check_date >= self.valid_from


class PriceSheetBackup(db.Model):
    """Backup/archive of a price sheet."""
    __tablename__ = 'price_sheet_backup'
    id = db.Column(db.Integer, primary_key=True)
    original_price_sheet_id = db.Column(db.Integer, db.ForeignKey('price_sheet.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    valid_from = db.Column(db.Date, nullable=True)
    valid_to = db.Column(db.Date, nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    backup_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    items = db.relationship('Item', 
        secondary=price_sheet_backup_items,
        backref=db.backref('price_sheet_backups', lazy='dynamic'),
        lazy='subquery'
    )

    def __init__(self, original_price_sheet_id, name, date, company_id, customer_id, items, valid_from=None, valid_to=None):
        self.original_price_sheet_id = original_price_sheet_id
        self.name = name
        self.date = date
        self.valid_from = valid_from
        self.valid_to = valid_to
        self.company_id = company_id
        self.customer_id = customer_id
        self.items = items
        self.backup_date = datetime.utcnow()

    def __repr__(self):
        return f"PriceSheetBackup('{self.name}', archived: {self.backup_date})"
