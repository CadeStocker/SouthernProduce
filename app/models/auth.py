# Copyright Cade Stocker 2026
"""Authentication and user-related models."""

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime


class Company(db.Model):
    """Organization/company information."""
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
    notifications = db.relationship('Notification', backref='company', lazy=True)
    admin_email = db.Column(db.String(120), unique=True, nullable=False)

    def __init__(self, name, admin_email):
        self.admin_email = admin_email
        self.name = name

    def __repr__(self):
        return f"Company('{self.name}')"


class User(db.Model, UserMixin):
    """User account information."""
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    notifications = db.relationship('Notification', backref='user', lazy=True, cascade='all, delete-orphan')

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
        from app import bcrypt
        
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
        from app import bcrypt
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def generate_reset_password_token(self):
        """Generate a password reset token."""
        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return serializer.dumps(self.email, salt=self.password)

    @staticmethod
    def verify_reset_password_token(token: str, user_id: int):
        """Verify a password reset token."""
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
        """Validate a password reset token."""
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


class Notification(db.Model):
    """User notifications."""
    __tablename__ = 'notification'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(20), nullable=False, default='info')
    link_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    read_at = db.Column(db.DateTime, nullable=True)

    def __init__(self, user_id, company_id, title, message, category='info', link_url=None, created_at=None, read_at=None):
        self.user_id = user_id
        self.company_id = company_id
        self.title = title
        self.message = message
        self.category = category
        self.link_url = link_url
        if created_at:
            self.created_at = created_at
        if read_at:
            self.read_at = read_at

    def __repr__(self):
        return f"Notification('{self.title}', '{self.user_id}', '{self.created_at}')"


class PendingUser(db.Model):
    """Users awaiting account confirmation."""
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


class APIKey(db.Model):
    """API keys for device authentication."""
    __tablename__ = 'api_key'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    device_name = db.Column(db.String(100), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)  # Optional expiration date
    
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


@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login."""
    if user_id is None:
        return None
    return User.query.get(user_id)
