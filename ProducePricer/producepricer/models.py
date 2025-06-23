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

class ItemDesignation(Enum):
    SNAKPAK = 'snakpak'
    RETAIL = 'retail'
    FOODSERVICE = 'foodservice'

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
    

item_raw = db.Table('item_raw',
    db.Column('item_id', db.Integer, db.ForeignKey('item.id'), primary_key=True),
    db.Column('raw_product_id', db.Integer, db.ForeignKey('raw_product.id'), primary_key=True)
)

# store the total cost of each item on a given date
# item_total_cost = db.Table('item_total_cost',
#     db.Column('item_id', db.Integer, db.ForeignKey('item.id'), primary_key=True),
#     db.Column('date', db.Date, primary_key=True)
# )

# table to store total costs of items on a given date
class ItemTotalCost(db.Model):
    __tablename__ = 'item_total_cost'
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    packaging_cost = db.Column(db.Float, nullable=False)  # cost of packaging for the item
    raw_product_cost = db.Column(db.Float, nullable=False)  # cost of raw products for the item
    labor_cost = db.Column(db.Float, nullable=False)  # labor cost for the item
    designation_cost = db.Column(db.Float, nullable=False)  # cost based on item designation
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, item_id, date, total_cost, packaging_cost, raw_product_cost, labor_cost, designation_cost, company_id):
        self.item_id = item_id
        self.date = date
        self.total_cost = total_cost
        self.packaging_cost = packaging_cost
        self.raw_product_cost = raw_product_cost
        self.labor_cost = labor_cost
        self.designation_cost = designation_cost
        self.company_id = company_id

    def __repr__(self):
        return f"ItemTotalCost('{self.item_id}', '{self.date}', '{self.total_cost}', '{self.packaging_cost}', '{self.raw_product_cost}', '{self.labor_cost}', '{self.designation_cost}')"
    
# table of each item we sell
class Item(db.Model):
    __tablename__ = 'item'
    raw_products = db.relationship('RawProduct', secondary=item_raw, backref=db.backref('items', lazy='dynamic'))
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(100), nullable=False) # REMOVED UNIQUE CONSTRAINT
    unit_of_weight = db.Column(db.Enum(UnitOfWeight), nullable=False)
    #weight = db.Column(db.Float, nullable=False)
    ranch = db.Column(db.Boolean, nullable=False, default=False)  # whether the item is a ranch item
    case_weight = db.Column(db.Float, nullable=False, default=0.0)  # weight of the case for the item
    packaging_id = db.Column(db.Integer, db.ForeignKey('packaging.id'), nullable=False) # changed to string
    item_designation = db.Column(db.Enum(ItemDesignation), nullable=False, default=ItemDesignation.RETAIL)  # added to specify the type of item
    # added to store raw product IDs for items that are made from multiple raw products
    #raw_product_ids = db.Column(db.ARRAY(db.Integer), nullable=True)  # Array of raw product IDs
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, name, code, unit_of_weight, packaging_id, company_id, case_weight=0.0, ranch=False, item_designation=ItemDesignation.FOODSERVICE, raw_product_ids=None):
        #self.raw_product_ids = db.cast(raw_product_ids, db.ARRAY(db.Integer)) if raw_product_ids is not None else db.cast([], db.ARRAY(db.Integer))
        self.name = name
        self.code = code
        self.unit_of_weight = unit_of_weight
        self.item_designation = item_designation
        #self.weight = weight
        self.packaging_id = packaging_id
        self.case_weight = case_weight
        self.ranch = ranch
        self.company_id = company_id

    def __repr__(self):
        return f"Item('{self.name}', '{self.code}', '{self.unit_of_weight}', '{self.weight}')"

# store ranch price
class RanchPrice(db.Model):
    __tablename__ = 'ranch_price'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    price = db.Column(db.Float, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, date, price, company_id):
        self.date = date
        self.price = price
        self.company_id = company_id

    def __repr__(self):
        return f"RanchPrice('{self.date}', '{self.price}')"


# store entries for items
class ItemInfo(db.Model):
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

# store entries of labor cost
class LaborCost(db.Model):
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

# changing this to just store price of an item given to a certain customer
# table of entries for price of each item
class PriceHistory(db.Model):
    __tablename__ = 'price_history'
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    #name = db.Column(db.String(100), nullable=False)
    #item_code = db.Column(db.String(100), nullable=False)
    # packaging_id is already in item table
    #packaging_id = db.Column(db.Integer, db.ForeignKey('packaging.id'), nullable=False)
    #packaging_cost = db.Column(db.Float, nullable=False) # just store the cost of the packaging
    #item_designation = db.Column(db.Enum(ItemDesignation), nullable=False)
    #raw_product_id = db.Column(db.Integer, db.ForeignKey('raw_product.id'), nullable=False)
    #ranch = db.Column(db.Boolean, nullable=False)
    #case_weight = db.Column(db.Float, nullable=False)
    
    def __init__(self, item_id, date, company_id, customer_id, price):
        self.item_id = item_id
        self.date = date
        self.company_id = company_id
        self.customer_id = customer_id
        self.price = price

    def __repr__(self):
        return f"PriceHistory('{self.item_id}', '{self.date}', '{self.company_id}', '{self.customer_id}', '{self.price}')"


# table to hold each raw product's information
class RawProduct(db.Model):
    __tablename__ = 'raw_product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    #unit_of_weight = db.Column(db.Enum(UnitOfWeight), nullable=False)
    #weight = db.Column(db.Float, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, name, company_id):
        self.name = name
        #self.unit_of_weight = unit_of_weight
        #self.weight = weight
        self.company_id = company_id

    def __repr__(self):
        return f"RawProduct('{self.name}', '{self.unit_of_weight}', '{self.weight}')"

# cost for a raw product on a given date
# COST IS BASED EXCLUSIVELY ON PRICE SENN SELLS TO US AT
class CostHistory(db.Model):
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
