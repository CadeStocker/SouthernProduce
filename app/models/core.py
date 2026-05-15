# Copyright Cade Stocker 2026
"""Core models and enums shared across the application."""

from enum import Enum
from app import db
from datetime import datetime


class UnitOfWeight(Enum):
    """Unit of weight measurements."""
    GRAM = 'gram'
    KILOGRAM = 'kilogram'
    POUND = 'pound'
    OUNCE = 'ounce'
    PINT = 'pint'
    LITER = 'liter'


class ItemDesignation(Enum):
    """Item designation/category types."""
    SNAKPAK = 'snakpak'
    RETAIL = 'retail'
    FOODSERVICE = 'foodservice'
    COMBO = 'combo'


class AIResponse(db.Model):
    """Store AI responses for reference and auditing."""
    __tablename__ = 'ai_response'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)  # optional name for the response
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, content, date, company_id, name=None):
        self.content = content
        self.date = date
        self.company_id = company_id
        self.name = name

    def __repr__(self):
        return f"AIResponse('{self.content[:50]}', '{self.date}')"


class Packaging(db.Model):
    """Packaging types available for products."""
    __tablename__ = 'packaging'
    id = db.Column(db.Integer, primary_key=True)
    packaging_type = db.Column(db.String(100), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, packaging_type, company_id):
        self.packaging_type = packaging_type
        self.company_id = company_id

    def __repr__(self):
        return f"Packaging('{self.packaging_type}')"


class PackagingCost(db.Model):
    """Costs for packaging components on a given date."""
    __tablename__ = 'packaging_cost'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    packaging_id = db.Column(db.Integer, db.ForeignKey('packaging.id'), nullable=False)
    box_cost = db.Column(db.Float, nullable=False)
    bag_cost = db.Column(db.Float, nullable=False)
    tray_andor_chemical_cost = db.Column(db.Float, nullable=False)
    label_andor_tape_cost = db.Column(db.Float, nullable=False)

    def __init__(self, box_cost, bag_cost, tray_andor_chemical_cost, label_andor_tape_cost, company_id, packaging_id, date):
        self.packaging_id = packaging_id
        self.date = date
        self.company_id = company_id
        self.box_cost = box_cost
        self.bag_cost = bag_cost
        self.tray_andor_chemical_cost = tray_andor_chemical_cost
        self.label_andor_tape_cost = label_andor_tape_cost

    def __repr__(self):
        return f"PackagingCost('{self.box_cost}', '{self.bag_cost}', '{self.tray_andor_chemical_cost}', '{self.label_andor_tape_cost}')"


class EmailTemplate(db.Model):
    """Email templates for communication."""
    __tablename__ = 'email_template'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)  # Jinja template syntax
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, name, subject, body, company_id, is_default=False):
        self.name = name
        self.subject = subject
        self.body = body
        self.is_default = is_default
        self.company_id = company_id

    def __repr__(self):
        return f"EmailTemplate('{self.name}', '{self.subject}', Default={self.is_default})"
