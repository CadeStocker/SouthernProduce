from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from producepricer import db, login_manager
from flask_login import UserMixin
from enum import Enum
from datetime import datetime

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
    COMBO = 'combo'

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
    
class AIResponse(db.Model):
    __tablename__ = 'ai_response'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)  # optional name for the response
    #user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, content, date, company_id, name=None):
        #self.user_id = user_id
        self.content = content
        self.date = date
        self.company_id = company_id
        self.name = name

    def __repr__(self):
        return f"AIResponse('{self.content[:50]}', '{self.date}')"
    
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
    
    def check_password(self, password: str) -> bool:
        """Verify a password against the hash.
        
        Supports both bcrypt hashed passwords and legacy plain text passwords.
        This allows gradual migration to encrypted passwords.
        """
        from producepricer import bcrypt
        
        # Try bcrypt verification first (for hashed passwords)
        try:
            if self.password.startswith('$2b$') or self.password.startswith('$2a$'):
                # This is a bcrypt hash
                return bcrypt.check_password_hash(self.password, password)
        except (ValueError, AttributeError):
            pass
        
        # Fall back to plain text comparison for legacy accounts
        # TODO: Remove this after all passwords are migrated to bcrypt
        return self.password == password
    
    def set_password(self, password: str):
        """Set the user's password (hashed with bcrypt)."""
        from producepricer import bcrypt
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def generate_reset_password_token(self):
        #self.password_hash = self.password  # Store the password hash for token generation

        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return serializer.dumps(self.email, salt=self.password)

    @staticmethod
    def verify_reset_password_token(token: str, user_id: int):
        user = User.query.get(user_id)

        if user is None:
            return None

        serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
        try:
            token_user_email = serializer.loads(
                token,
                max_age=current_app.config["RESET_PASS_TOKEN_MAX_AGE"],
                salt=user.password,
            )
        except (BadSignature, SignatureExpired):
            return None

        if token_user_email != user.email:
            return None

        return user
    
    @staticmethod
    def validate_reset_password_token(token: str, user_id: int):
        user = User.query.get(user_id)

        if user is None:
            return None

        serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
        try:
            token_user_email = serializer.loads(
                token,
                max_age=current_app.config["RESET_PASS_TOKEN_MAX_AGE"],
                salt=user.password,
            )
        except (BadSignature, SignatureExpired):
            return None

        if token_user_email != user.email:
            return None

        return user

item_raw = db.Table('item_raw',
    db.Column('item_id', db.Integer, db.ForeignKey('item.id'), primary_key=True),
    db.Column('raw_product_id', db.Integer, db.ForeignKey('raw_product.id'), primary_key=True)
)

# store the total cost of each item on a given date
# item_total_cost = db.Table('item_total_cost',
#     db.Column('item_id', db.Integer, db.ForeignKey('item.id'), primary_key=True),
#     db.Column('date', db.Date, primary_key=True)
# )

@login_manager.user_loader
def load_user(user_id):
    if user_id is None:
        return None
    return User.query.get(user_id)

# table to store total costs of items on a given date
class ItemTotalCost(db.Model):
    # ranch cost exists here, but deployed version says it doesn't
    __tablename__ = 'item_total_cost'
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    ranch_cost = db.Column(db.Float, nullable=False)  # cost of ranch items
    total_cost = db.Column(db.Float, nullable=False)
    packaging_cost = db.Column(db.Float, nullable=False)  # cost of packaging for the item
    raw_product_cost = db.Column(db.Float, nullable=False)  # cost of raw products for the item
    labor_cost = db.Column(db.Float, nullable=False)  # labor cost for the item
    designation_cost = db.Column(db.Float, nullable=False)  # cost based on item designation
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, item_id, date, total_cost, ranch_cost, packaging_cost, raw_product_cost, labor_cost, designation_cost, company_id):
        self.item_id = item_id
        self.date = date
        self.total_cost = total_cost
        self.ranch_cost = ranch_cost  # cost of ranch items
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
    # alternate code ADDED FOR SENN
    alternate_code = db.Column(db.String(100), nullable=True)  # added to store alternate codes for items
    #weight = db.Column(db.Float, nullable=False)
    ranch = db.Column(db.Boolean, nullable=False, default=False)  # whether the item is a ranch item
    case_weight = db.Column(db.Float, nullable=False, default=0.0)  # weight of the case for the item
    packaging_id = db.Column(db.Integer, db.ForeignKey('packaging.id'), nullable=False) # changed to string
    item_designation = db.Column(db.Enum(ItemDesignation), nullable=False, default=ItemDesignation.RETAIL)  # added to specify the type of item
    # added to store raw product IDs for items that are made from multiple raw products
    #raw_product_ids = db.Column(db.ARRAY(db.Integer), nullable=True)  # Array of raw product IDs
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, name, code, unit_of_weight, packaging_id, company_id, case_weight=0.0, ranch=False, item_designation=ItemDesignation.FOODSERVICE, raw_product_ids=None, alternate_code=None):
        #self.raw_product_ids = db.cast(raw_product_ids, db.ARRAY(db.Integer)) if raw_product_ids is not None else db.cast([], db.ARRAY(db.Integer))
        self.name = name
        #self.alternate_code = alternate_code
        self.code = code
        self.unit_of_weight = unit_of_weight
        self.item_designation = item_designation
        #self.weight = weight
        self.packaging_id = packaging_id
        self.case_weight = case_weight
        self.ranch = ranch
        self.company_id = company_id
        self.alternate_code = alternate_code  # added to store alternate codes for items

    def __repr__(self):
        return f"Item('{self.name}', '{self.alternate_code}', '{self.code}', '{self.unit_of_weight}', '{self.case_weight}', '{self.packaging_id}', '{self.item_designation}')"

# designation cost
class DesignationCost(db.Model):
    __tablename__ = 'designation_cost'
    id = db.Column(db.Integer, primary_key=True)
    item_designation = db.Column(db.Enum(ItemDesignation), nullable=False)
    cost = db.Column(db.Float, nullable=False)  # cost based on item designation
    date = db.Column(db.Date, nullable=False)  # date of the cost
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, item_designation, cost, date, company_id):
        self.item_designation = item_designation
        self.cost = cost
        self.date = date
        self.company_id = company_id

    def __repr__(self):
        return f"DesignationCost('{self.item_designation}', '{self.cost}', '{self.date}')"

# store ranch price
class RanchPrice(db.Model):
    __tablename__ = 'ranch_price'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    cost = db.Column(db.Float, nullable=False)  # cost of the ranch item
    price = db.Column(db.Float, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    def __init__(self, date, cost, price, company_id):
        self.date = date
        self.cost = cost  # cost of the ranch item
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
    
    def __init__(self, item_id, date, company_id, customer_id, price):
        self.item_id = item_id
        self.date = date
        self.company_id = company_id
        self.customer_id = customer_id
        self.price = price

    def __repr__(self):
        return f"PriceHistory('{self.item_id}', '{self.date}', '{self.company_id}', '{self.customer_id}', '{self.price}')"

# association table for PriceSheet ↔ Item
price_sheet_items = db.Table(
    'price_sheet_items',
    db.Column('price_sheet_id', db.Integer, db.ForeignKey('price_sheet.id'), primary_key=True),
    db.Column('item_id',         db.Integer, db.ForeignKey('item.id'),        primary_key=True)
)

# hold all the items for a price sheet
class PriceSheet(db.Model):
    __tablename__ = 'price_sheet'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)  # Keep for backwards compatibility, or can deprecate later
    valid_from = db.Column(db.Date, nullable=True)  # Start date of price sheet validity
    valid_to = db.Column(db.Date, nullable=True)    # End date of price sheet validity
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    #item_ids = db.relationship('Item', secondary='price_sheet_items', backref=db.backref('price_sheets', lazy='dynamic'))
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)

    items = db.relationship('Item', 
        secondary=price_sheet_items,
        backref=db.backref('price_sheets', lazy='dynamic'),
        lazy='subquery'
    )

    def __init__(self, name, date, company_id, customer_id, valid_from=None, valid_to=None):
        self.name = name
        self.date = date
        self.valid_from = valid_from if valid_from else date  # Default to date if not provided
        self.valid_to = valid_to
        self.company_id = company_id
        self.customer_id = customer_id
        #self.item_ids = items  # list of Item objects

    def __repr__(self):
        if self.valid_from and self.valid_to:
            return f"PriceSheet('{self.name}', valid: {self.valid_from} to {self.valid_to})"
        return f"PriceSheet('{self.name}', '{self.date}')"
    
    def is_valid_on_date(self, check_date):
        """Check if this price sheet is valid on a given date."""
        if not self.valid_from:
            # If no validity range set, use the single date field
            return self.date == check_date
        
        # Check if date is within the validity range
        if self.valid_to:
            return self.valid_from <= check_date <= self.valid_to
        else:
            # If no end date, valid from start date onwards
            return check_date >= self.valid_from

# association table for PriceSheetBackup ↔ Item
price_sheet_backup_items = db.Table(
    'price_sheet_backup_items',
    db.Column('price_sheet_backup_id', db.Integer, db.ForeignKey('price_sheet_backup.id'), primary_key=True),
    db.Column('item_id',               db.Integer, db.ForeignKey('item.id'),              primary_key=True)
)

# backup of a price sheet
class PriceSheetBackup(db.Model):
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

class PendingUser(db.Model):
    __tablename__ = 'pending_user'
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
        return f"PendingUser('{self.first_name}', '{self.last_name}', '{self.email}')"

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
    email = db.Column(db.String(120), nullable=True)  # Primary email (optional, kept for backwards compatibility)
    # boolean of whether they are the master customer
    is_master = db.Column(db.Boolean, default=False, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    # Relationship to multiple emails
    emails = db.relationship('CustomerEmail', backref='customer', lazy=True, cascade='all, delete-orphan')

    def __init__(self, name, email, company_id):
        self.company_id = company_id
        self.name = name
        self.email = email

    def __repr__(self):
        return f"Customer('{self.name}', '{self.email}')"
    
    def get_all_emails(self):
        """Return list of all email addresses for this customer (primary + additional)"""
        all_emails = []
        if self.email:
            all_emails.append(self.email)
        for ce in self.emails:
            if ce.email and ce.email not in all_emails:
                all_emails.append(ce.email)
        return all_emails


class CustomerEmail(db.Model):
    """Model to store multiple email addresses for a customer"""
    __tablename__ = 'customer_email'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    label = db.Column(db.String(50), nullable=True)  # e.g., "Billing", "Sales", "Primary Contact"
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    
    def __init__(self, email, customer_id, label=None):
        self.email = email
        self.customer_id = customer_id
        self.label = label

    def __repr__(self):
        return f"CustomerEmail('{self.email}', '{self.label}')"


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

def generate_reset_password_token(self):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

    return serializer.dumps(self.email, salt=self.password)

class EmailTemplate(db.Model):
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

class BrandName(db.Model):
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


class ReceivingLog(db.Model):
    __tablename__ = 'receiving_log'
    id = db.Column(db.Integer, primary_key=True)
    raw_product_id = db.Column(db.Integer, db.ForeignKey('raw_product.id'), nullable=False)
    pack_size_unit = db.Column(db.String(50), nullable=False) # can be in pounds or count (number of items in box)
    pack_size = db.Column(db.Float, nullable=False)
    brand_name_id = db.Column(db.Integer, db.ForeignKey('brand_name.id'), nullable=False) 
    quantity_received = db.Column(db.Integer, nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('seller.id'), nullable=False) 
    temperature = db.Column(db.Float, nullable=False)
    hold_or_used = db.Column(db.String(20), nullable=False) # choices are 'hold' or 'used'
    datetime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    grower_or_distributor_id = db.Column(db.Integer, db.ForeignKey('grower_or_distributor.id'), nullable=False)
    country_of_origin = db.Column(db.String(100), nullable=False) 
    received_by = db.Column(db.String(100), nullable=False) # employee's name who made the log entry
    returned = db.Column(db.String(100), nullable=True) # this doesn't appear in most entries, and when it does it's an employee's name
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    price_paid = db.Column(db.Float, nullable=True) # price paid for the product received (per unit of pack_size)

    # Relationships
    raw_product = db.relationship('RawProduct', backref='receiving_logs')
    brand_name = db.relationship('BrandName', backref='receiving_logs')
    seller = db.relationship('Seller', backref='receiving_logs')
    grower_or_distributor = db.relationship('GrowerOrDistributor', backref='receiving_logs')
    images = db.relationship('ReceivingImage', backref='receiving_log', lazy=True, cascade='all, delete-orphan')
    
    def __init__(self, raw_product_id, pack_size_unit, pack_size, brand_name_id, quantity_received, seller_id, temperature, hold_or_used, grower_or_distributor_id, country_of_origin, received_by, company_id, returned=None, date_time=None, price_paid=None):
        self.raw_product_id = raw_product_id
        self.pack_size_unit = pack_size_unit
        self.pack_size = pack_size
        self.brand_name_id = brand_name_id
        self.quantity_received = quantity_received
        self.seller_id = seller_id
        self.temperature = temperature
        self.hold_or_used = hold_or_used
        self.grower_or_distributor_id = grower_or_distributor_id
        self.country_of_origin = country_of_origin
        self.received_by = received_by
        self.company_id = company_id
        self.returned = returned
        self.price_paid = price_paid
        if date_time:
            self.datetime = date_time
    
    def get_master_customer_price(self):
        """Get the market cost for this raw product around the time of this receiving log.
        This looks at the most recent cost entry in CostHistory for comparison.
        Returns a tuple of (cost, date) or None if no cost found."""
        from datetime import timedelta
        from sqlalchemy import and_
        
        # Calculate the date of this receiving log
        log_date = self.datetime.date() if self.datetime else None
        if not log_date:
            return None
        
        # Look for the most recent cost entry for this raw product on or before the receiving log date
        # We'll search within a 30-day window before the log date to find recent market cost
        search_start = log_date - timedelta(days=30)
        
        cost_entry = CostHistory.query.filter(
            and_(
                CostHistory.raw_product_id == self.raw_product_id,
                CostHistory.company_id == self.company_id,
                CostHistory.date <= log_date,
                CostHistory.date >= search_start
            )
        ).order_by(CostHistory.date.desc()).first()
        
        return (cost_entry.cost, cost_entry.date) if cost_entry else None
    
    def get_price_comparison(self):
        """Compare the price paid to the market cost and return a dict with comparison info."""
        if self.price_paid is None:
            return None
        
        market_data = self.get_master_customer_price()
        if market_data is None:
            return {
                'price_paid': self.price_paid,
                'master_price': None,
                'market_date': None,
                'difference': None,
                'percentage': None,
                'status': 'no_market_data'
            }
        
        market_cost, market_date = market_data
        difference = self.price_paid - market_cost
        percentage = (difference / market_cost * 100) if market_cost > 0 else 0
        
        if abs(difference) < 0.01:  # Within 1 cent
            status = 'at_market'
        elif difference > 0:
            status = 'above_market'
        else:
            status = 'below_market'
        
        return {
            'price_paid': self.price_paid,
            'master_price': market_cost,  # This is actually the market cost from CostHistory
            'market_date': market_date,
            'difference': difference,
            'percentage': percentage,
            'status': status
        }
        
    def __repr__(self):
        return f"ReceivingLog('{self.datetime}', '{self.raw_product_id}', '{self.quantity_received}')"

class ReceivingImage(db.Model):
    __tablename__ = 'receiving_image'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    receiving_log_id = db.Column(db.Integer, db.ForeignKey('receiving_log.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __init__(self, filename, receiving_log_id, company_id):
        self.filename = filename
        self.receiving_log_id = receiving_log_id
        self.company_id = company_id

    def __repr__(self):
        return f"ReceivingImage('{self.filename}', '{self.receiving_log_id}')"

class APIKey(db.Model):
    """Model for storing API keys for device authentication."""
    __tablename__ = 'api_key'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    device_name = db.Column(db.String(100), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    company = db.relationship('Company', backref='api_keys')
    created_by = db.relationship('User', backref='created_api_keys')

    def __init__(self, key, device_name, company_id, created_by_user_id):
        self.key = key
        self.device_name = device_name
        self.company_id = company_id
        self.created_by_user_id = created_by_user_id

    def __repr__(self):
        return f"APIKey('{self.device_name}', active={self.is_active})"
    
    @staticmethod
    def generate_key():
        """Generate a secure random API key."""
        import secrets
        return secrets.token_urlsafe(48)
    
    def update_last_used(self):
        """Update the last_used_at timestamp."""
        self.last_used_at = datetime.utcnow()
        db.session.commit()
    
    def revoke(self):
        """Deactivate this API key."""
        self.is_active = False
        db.session.commit()
    
    def activate(self):
        """Reactivate this API key."""
        self.is_active = True
        db.session.commit()

class ItemInventory(db.Model):
    """Model for tracking inventory counts of items from the iPad app."""
    __tablename__ = 'inventory_count'
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    count_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    counted_by = db.Column(db.String(200), nullable=True)  # Name of person who counted
    notes = db.Column(db.String(500), nullable=True)  # Optional notes about the count
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    
    # Relationships
    item = db.relationship('Item', backref='inventory_counts')
    
    def __init__(self, item_id, quantity, company_id, count_date=None, counted_by=None, notes=None):
        self.item_id = item_id
        self.quantity = quantity
        self.company_id = company_id
        self.counted_by = counted_by
        self.notes = notes
        if count_date:
            self.count_date = count_date
    
    def __repr__(self):
        return f"ItemInventory(item_id={self.item_id}, quantity={self.quantity}, date={self.count_date})"