from producepricer import db, login_manager
from flask_login import UserMixin
from enum import Enum

@login_manager.user_loader
def load_user(user_id):
    if user_id is None:
        return None
    return User.query.get(user_id)

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
    customers = db.relationship('Customer', backref='company', lazy=True)
    packaging = db.relationship('Packaging', backref='company', lazy=True)
    packaging_cost = db.relationship('PackagingCost', backref='company', lazy=True)
    admin_email = db.Column(db.String(120), unique=True, nullable=False)

    def __init__(self, name, admin_email):
        self.admin_email = admin_email
        self.name = name

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

    def __init__(self, first_name, last_name, email, password, company_id):
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.password = password
        self.company_id = company_id

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
    packaging_id = db.Column(db.Integer, db.ForeignKey('packaging.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, name, code, unit_of_weight, weight, company_id):
        self.name = name
        self.code = code
        self.unit_of_weight = unit_of_weight
        self.weight = weight
        self.company_id = company_id

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
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)

    def __init__(self, price_per_unit, date, company_id, item_id, customer_id):
        self.item_id = item_id
        self.price_per_unit = price_per_unit
        self.date = date
        self.company_id = company_id
        self.customer_id = customer_id

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

    def __init__(self, name, unit_of_weight, weight, company_id):
        self.name = name
        self.unit_of_weight = unit_of_weight
        self.weight = weight
        self.company_id = company_id

    def __repr__(self):
        return f"RawProduct('{self.name}', '{self.unit_of_weight}', '{self.weight}')"
    
# COST IS BASED EXCLUSIVELY ON PRICE SENN SELLS TO US AT
class CostHistory(db.Model):
    __tablename__ = 'cost_history'
    id = db.Column(db.Integer, primary_key=True)
    raw_product_id = db.Column(db.Integer, db.ForeignKey('raw_product.id'), nullable=False)
    cost = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, cost, date, company_id, raw_product_id):
        self.raw_product_id = raw_product_id
        self.cost = cost
        self.date = date
        self.company_id = company_id

    def __repr__(self):
        return f"CostHistory('{self.cost}', '{self.date}')"
    
class Customer(db.Model):
    __tablename__ = 'customer'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, name, email, company_id):
        self.company_id = company_id
        self.name = name
        self.email = email

    def __repr__(self):
        return f"Customer('{self.name}', '{self.email}')"

class Packaging(db.Model):
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
    __tablename__ = 'packaging_cost'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    packaging_id = db.Column(db.Integer, db.ForeignKey('packaging.id'), nullable=False)
    box_cost = db.Column(db.Float, nullable=False)
    bag_cost = db.Column(db.Float, nullable=False)
    tray_andor_chemical_cost = db.Column(db.Float, nullable=False)
    label_andor_tape_cost = db.Column(db.Float, nullable=False)

    def __init__(self, box_cost, bag_cost, tray_andor_chemical_cost, label_andor_tape_cost):
        self.box_cost = box_cost
        self.bag_cost = bag_cost
        self.tray_andor_chemical_cost = tray_andor_chemical_cost
        self.label_andor_tape_cost = label_andor_tape_cost

    def __repr__(self):
        return f"PackagingCost('{self.box_cost}', '{self.bag_cost}', '{self.tray_andor_chemical_cost}', '{self.label_andor_tape_cost}')"
