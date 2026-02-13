
import pytest
from producepricer import db

from datetime import date
from producepricer.models import RawProduct, CostHistory, Packaging

def _seed_data(company_id):
    packaging = Packaging(packaging_type="Test Box", company_id=company_id)
    raw1 = RawProduct(name="Raw A", company_id=company_id)
    raw2 = RawProduct(name="Raw B", company_id=company_id)
    db.session.add_all([packaging, raw1, raw2])
    db.session.flush()
    
    # Cost history
    ch1 = CostHistory(raw_product_id=raw1.id, cost=29.95, date=date(2024, 1, 1), company_id=company_id)
    ch2 = CostHistory(raw_product_id=raw2.id, cost=29.95, date=date(2024, 1, 1), company_id=company_id)
    db.session.add_all([ch1, ch2])
    db.session.commit()
    
    return packaging, [raw1, raw2]

def test_manual_raw_cost_override(client, logged_in_user, app):
    with app.app_context():
        # Setup data
        packaging, raw_products = _seed_data(logged_in_user.company_id)
        raw_ids = [r.id for r in raw_products]
        packaging_id = packaging.id

        # Prepare form data
        data = {
            'action': 'calculate',
            'packaging': packaging_id,
            'raw_products': raw_ids,
            'raw_product_cost': 30.00,  # User overrides 29.95 avg to 30.00
            'product_yield': 100,
            'labor_hours': 1,
            'ranch': False,
            'case_weight': 10,
            'item_designation': 'RETAIL',
        }

        # In tests checking form submission often requires either disabling CSRF or mocking.
        # Assuming CSRF is disabled in test config or we need to fetch it first.

        # Let's try posting.
        response = client.post('/price_quoter', data=data, follow_redirects=True)
        text = response.get_data(as_text=True)

        # Iterate result to find "Raw Cost"
        # With the new logic, the input raw_product_cost is the TOTAL cost (SUM), not average.
        # So if we input 30.00, the raw cost should be 30.00.

        assert "Raw Cost: $30.0" in text, f"Expected Raw Cost: $30.00 in response text but found something else. \nFull Text snippet: {text[text.find('Raw Cost:'):text.find('Raw Cost:')+100]}"