# Copyright Cade Stocker 2026
"""Supplier-related models."""

from app import db


class BrandName(db.Model):
    """Brand names for products."""
    __tablename__ = 'brand_name'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, name, company_id):
        self.name = name
        self.company_id = company_id

    def __repr__(self):
        return f"BrandName('{self.name}')"


class Seller(db.Model):
    """Sellers/vendors."""
    __tablename__ = 'seller'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, name, company_id):
        self.name = name
        self.company_id = company_id

    def __repr__(self):
        return f"Seller('{self.name}')"


class GrowerOrDistributor(db.Model):
    """Growers or distributors of raw products."""
    __tablename__ = 'grower_or_distributor'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String, nullable=False)
    state = db.Column(db.String, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, name, company_id, city, state):
        self.name = name
        self.company_id = company_id
        self.city = city
        self.state = state

    def __repr__(self):
        return f"GrowerOrDistributor('{self.name}')"
