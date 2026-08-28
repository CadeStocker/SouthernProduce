# Copyright Cade Stocker 2026
"""Models for anomaly detection and incremental statistics."""

from datetime import datetime
from app import db

"""
Will use EWMA to keep ongoing stats for each (mean, var, stddev) for each (entity, metric, window)

From this, we can compute z-scores to find outliers in data as soon as they're added. 
The idea is for this to trigger the app's notifications system, 
and then for the anomolies to be converted to plain text explanations later if desired.
"""


class EntityStat(db.Model):
    """Rolling statistics for an (entity, metric, window)."""
    __tablename__ = 'entity_stat'
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(100), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    metric = db.Column(db.String(100), nullable=False)
    window = db.Column(db.String(50), nullable=False, default='ewma') # window is a string of representing what method was used (ewma, etc.)
    mean = db.Column(db.Float, nullable=True)
    stddev = db.Column(db.Float, nullable=True)
    count = db.Column(db.Integer, nullable=False, default=0)
    last_value = db.Column(db.Float, nullable=True)
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def update_ewma(self, new_value, alpha=0.1):
        """Update mean/stddev using EWMA incremental formulas.

        formula for updates: 
        alpha * new_value + (1 - alpha) * old_mean

        Uses the form from the spec. If no previous stats exist, initialize
        mean to new_value and stddev to 0.
        """
        
        if self.mean is None or self.count == 0:
            self.mean = float(new_value)
            self.stddev = 0.0
            self.count = 1
            self.last_value = float(new_value)
            self.last_updated = datetime.utcnow()
            return

        old_mean = self.mean
        old_var = (self.stddev or 0.0) ** 2
        new_mean = alpha * float(new_value) + (1 - alpha) * old_mean

        # update variance per EWMA formula
        new_var = (1 - alpha) * (old_var + alpha * (float(new_value) - old_mean) ** 2)
        
        self.mean = new_mean
        self.stddev = (new_var ** 0.5)
        self.count = self.count + 1
        self.last_value = float(new_value)
        self.last_updated = datetime.utcnow()


class Anomaly(db.Model):
    """Detected anomaly record."""
    __tablename__ = 'anomaly'
    id = db.Column(db.Integer, primary_key=True)
    # Which business area this anomaly belongs to; see services.analytics_domains.
    # Nullable so rows detected before domains existed still load.
    domain = db.Column(db.String(32), nullable=True, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True, index=True)
    entity_type = db.Column(db.String(100), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    metric = db.Column(db.String(100), nullable=False)
    expected_value = db.Column(db.Float, nullable=True)
    actual_value = db.Column(db.Float, nullable=True)
    z_score = db.Column(db.Float, nullable=True)
    rule_triggered = db.Column(db.String(100), nullable=True)
    severity = db.Column(db.String(20), nullable=False, default='low')
    dollar_impact = db.Column(db.Float, nullable=True)
    explanation = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='open', index=True)
    detected_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fixed_at = db.Column(db.DateTime, nullable=True)
    fixed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    reviewed_by = db.relationship('User', foreign_keys=[reviewed_by_id], backref='anomalies_reviewed')
    fixed_by = db.relationship('User', foreign_keys=[fixed_by_id], backref='anomalies_fixed')


class JobRun(db.Model):
    """Watermark tracking for incremental runs per source table."""
    __tablename__ = 'job_run'
    id = db.Column(db.Integer, primary_key=True)
    source_table = db.Column(db.String(200), nullable=False, unique=True)
    last_processed_id = db.Column(db.BigInteger, nullable=True)
    last_processed_at = db.Column(db.DateTime, nullable=True)
    last_run_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def touch(self, last_id=None, last_at=None):
        if last_id is not None:
            self.last_processed_id = int(last_id)
        if last_at is not None:
            self.last_processed_at = last_at
        self.last_run_at = datetime.utcnow()
