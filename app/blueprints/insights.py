from flask import Blueprint, render_template, request
from flask_login import login_required
from app.models import Anomaly

insights = Blueprint('insights', __name__)


@insights.route('/data_insights')
@login_required
def data_insights():
    """List recent data insights / anomalies."""
    # basic list: most recent 200
    anomalies = Anomaly.query.order_by(Anomaly.detected_at.desc()).limit(200).all()
    return render_template('data_insights.html', anomalies=anomalies)
