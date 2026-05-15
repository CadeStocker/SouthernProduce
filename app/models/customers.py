# Copyright Cade Stocker 2026
"""Customer-related models."""

from app import db


class Customer(db.Model):
    """Customer information."""
    __tablename__ = 'customer'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    is_master = db.Column(db.Boolean, default=False, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    emails = db.relationship('CustomerEmail', backref='customer', lazy=True, cascade='all, delete-orphan')

    def __init__(self, name, email, company_id):
        self.company_id = company_id
        self.name = name
        self.email = email

    def __repr__(self):
        return f"Customer('{self.name}', '{self.email}')"
    
    def get_all_emails(self):
        """Return list of all email addresses for this customer."""
        all_emails = []
        if self.email:
            all_emails.append(self.email)
        for ce in self.emails:
            if ce.email and ce.email not in all_emails:
                all_emails.append(ce.email)
        return all_emails


class CustomerEmail(db.Model):
    """Additional email addresses for a customer."""
    __tablename__ = 'customer_email'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    label = db.Column(db.String(50), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    
    def __init__(self, email, customer_id, label=None):
        self.email = email
        self.customer_id = customer_id
        self.label = label

    def __repr__(self):
        return f"CustomerEmail('{self.email}', '{self.label}')"
