# Copyright Cade Stocker 2026
"""Cost-related models."""

from app import db
from datetime import datetime


class LaborCost(db.Model):
    """Labor cost for a given date."""
    __tablename__ = 'labor_cost'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    labor_cost = db.Column(db.Float, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, date, labor_cost, company_id):
        self.date = date
        self.labor_cost = labor_cost
        self.company_id = company_id
        
    def __repr__(self):
        return f"LaborCost('{self.date}', '{self.labor_cost}')"


class CostHistory(db.Model):
    """Historical cost for a raw product."""
    __tablename__ = 'cost_history'
    id = db.Column(db.Integer, primary_key=True)
    raw_product_id = db.Column(db.Integer, db.ForeignKey('raw_product.id'), nullable=False)
    cost = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, cost, date, company_id, raw_product_id):
        self.raw_product_id = raw_product_id
        self.cost = cost
        self.date = date
        self.company_id = company_id

    def __repr__(self):
        return f"CostHistory('{self.cost}', '{self.date}')"
