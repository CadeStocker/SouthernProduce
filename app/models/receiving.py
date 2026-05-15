# Copyright Cade Stocker 2026
"""Receiving log and related models."""

from app import db
from datetime import datetime, timedelta
from sqlalchemy import and_


class ReceivingLog(db.Model):
    """Log entry for received raw materials."""
    __tablename__ = 'receiving_log'
    id = db.Column(db.Integer, primary_key=True)
    raw_product_id = db.Column(db.Integer, db.ForeignKey('raw_product.id'), nullable=False)
    pack_size_unit = db.Column(db.String(50), nullable=False)
    pack_size = db.Column(db.Float, nullable=False)
    brand_name_id = db.Column(db.Integer, db.ForeignKey('brand_name.id'), nullable=False) 
    quantity_received = db.Column(db.Integer, nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('seller.id'), nullable=False) 
    temperature = db.Column(db.Float, nullable=False)
    hold_or_used = db.Column(db.String(20), nullable=False)
    datetime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    grower_or_distributor_id = db.Column(db.Integer, db.ForeignKey('grower_or_distributor.id'), nullable=False)
    country_of_origin = db.Column(db.String(100), nullable=False) 
    received_by = db.Column(db.String(100), nullable=False)
    returned = db.Column(db.String(100), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    price_paid = db.Column(db.Float, nullable=True)

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
        """Get the market cost for this raw product around the time of this receiving log."""
        from app.models.costing import CostHistory
        
        log_date = self.datetime.date() if self.datetime else None
        if not log_date:
            return None
        
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
        """Compare the price paid to the market cost."""
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
        
        if abs(difference) < 0.01:
            status = 'at_market'
        elif difference > 0:
            status = 'above_market'
        else:
            status = 'below_market'
        
        return {
            'price_paid': self.price_paid,
            'master_price': market_cost,
            'market_date': market_date,
            'difference': difference,
            'percentage': percentage,
            'status': status
        }
        
    def __repr__(self):
        return f"ReceivingLog('{self.datetime}', '{self.raw_product_id}', '{self.quantity_received}')"


class ReceivingImage(db.Model):
    """Images associated with a receiving log."""
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
