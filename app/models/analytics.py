# Copyright Cade Stocker 2026
"""Shared fact model for cross-domain analytics.

Created by claude sonnet aug 27 2026, reviewed by Cade Stocker aug 27, 2026
"""

from datetime import date

from app import db


class AnalyticsFact(db.Model):
    """A denormalized, additive fact used by reports and insight jobs.

    A row represents one grain of a business event or snapshot. Dimensions that
    do not apply to a fact type remain NULL; measures default to zero so facts
    can be aggregated consistently across sources.
    """

    __tablename__ = 'analytics_fact'
    __table_args__ = (
        db.CheckConstraint(
            "fact_type IN ('item_sale', 'cost_margin', 'receiving', 'labor', 'inventory_snapshot', 'customer_order')",
            name='ck_analytics_fact_type',
        ),
        db.UniqueConstraint(
            'fact_type', 'source_table', 'source_id',
            name='uq_analytics_fact_source',
        ),
    )

    # as mentioned previously, non applicable fields are filled in with NULL
    id = db.Column(db.Integer, primary_key=True)
    fact_type = db.Column(db.String(32), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True, default=date.today)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False, index=True)
    location = db.Column(db.String(100), nullable=True)

    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=True, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('grower_or_distributor.id'), nullable=True, index=True)
    raw_product_id = db.Column(db.Integer, db.ForeignKey('raw_product.id'), nullable=True, index=True)

    quantity = db.Column(db.Float, nullable=False, default=0.0)
    revenue = db.Column(db.Float, nullable=False, default=0.0)
    cost = db.Column(db.Float, nullable=False, default=0.0)
    margin = db.Column(db.Float, nullable=False, default=0.0)
    labor_hours = db.Column(db.Float, nullable=False, default=0.0)

    source_table = db.Column(db.String(100), nullable=True)
    source_id = db.Column(db.BigInteger, nullable=True)

    def __init__(self, fact_type, company_id, date=None, **measures):
        self.fact_type = fact_type
        self.company_id = company_id
        if date is not None:
            self.date = date

        for field in (
            'location', 'item_id', 'customer_id', 'supplier_id',
            'raw_product_id', 'quantity', 'revenue', 'cost', 'margin',
            'labor_hours', 'source_table', 'source_id',
        ):
            if field in measures:
                setattr(self, field, measures[field])

    def __repr__(self):
        return f"AnalyticsFact('{self.fact_type}', '{self.date}', company_id={self.company_id})"