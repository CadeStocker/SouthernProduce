from flask_sqlalchemy import SQLAlchemy
from producepricer import db
from flask_login import UserMixin
from flask import Flask, redirect, render_template, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from enum import Enum

# might remove this
class UnitOfWeight(Enum):
    GRAM = 'gram'
    KILOGRAM = 'kilogram'
    POUND = 'pound'
    OUNCE = 'ounce'
    PINT = 'pint'
    LITER = 'liter'

# table of companies
class Company(db.Model):
    __tablename__ = 'company'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    users = db.relationship('User', backref='company', lazy=True)
    items = db.relationship('Item', backref='company', lazy=True)
    raw_products = db.relationship('RawProduct', backref='company', lazy=True)
    cost_history = db.relationship('CostHistory', backref='company', lazy=True)
    price_history = db.relationship('PriceHistory', backref='company', lazy=True)

    def __repr__(self):
        return f"Company('{self.name}')"
    
# table of users
class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __repr__(self):
        return f"User('{self.first_name}', '{self.last_name}', '{self.email}')"
    
# table of each item we sell
class Item(db.Model):
    __tablename__ = 'item'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(100), unique=True, nullable=False)
    unit_of_weight = db.Column(db.Enum(UnitOfWeight), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __repr__(self):
        return f"Item('{self.name}', '{self.unit_of_weight}', '{self.price_per_unit}')"

# table of entries for price of each item
class PriceHistory(db.Model):
    __tablename__ = 'price_history'
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __repr__(self):
        return f"PriceHistory('{self.price_per_unit}', '{self.date}')"

# table to hold each raw product's information
class RawProduct(db.Model):
    __tablename__ = 'raw_product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    unit_of_weight = db.Column(db.Enum(UnitOfWeight), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __repr__(self):
        return f"RawProduct('{self.name}', '{self.unit_of_weight}', '{self.weight}')"
    
# COST IS BASED EXCLUSIVELY ON PRICE SENN SELLS TO US AT
class CostHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    raw_product_id = db.Column(db.Integer, db.ForeignKey('raw_product.id'), nullable=False)
    cost = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __repr__(self):
        return f"CostHistory('{self.cost}', '{self.date}')"