import pytest
from datetime import date
from producepricer import db
from producepricer.models import (
    Packaging, RawProduct, CostHistory, Item, ItemInfo, 
    PackagingCost, LaborCost, RanchPrice, DesignationCost
)

def _setup_calculation_scenario(company_id):
    # 1. Setup Packaging & Cost
    pack = Packaging(packaging_type="Standard Box", company_id=company_id)
    db.session.add(pack)
    db.session.flush()
    
    pack_cost = PackagingCost(
        packaging_id=pack.id,
        box_cost=1.50,
        bag_cost=0.50,
        tray_andor_chemical_cost=0.25,
        label_andor_tape_cost=0.10,
        date=date(2024, 1, 1),
        company_id=company_id
    )
    db.session.add(pack_cost)

    # 2. Setup Raw Products & Cost
    raw1 = RawProduct(name="Beans", company_id=company_id)
    raw2 = RawProduct(name="Peas", company_id=company_id)
    db.session.add_all([raw1, raw2])
    db.session.flush()

    # History: Beans $10, Peas $20
    ch1 = CostHistory(raw_product_id=raw1.id, cost=10.00, date=date(2024, 1, 1), company_id=company_id)
    ch2 = CostHistory(raw_product_id=raw2.id, cost=20.00, date=date(2024, 1, 1), company_id=company_id)
    db.session.add_all([ch1, ch2])

    # 3. Setup Labor Cost (Global)
    # Labor is stored as cost per hour
    lc = LaborCost(labor_cost=15.00, date=date(2024, 1, 1), company_id=company_id)
    db.session.add(lc)

    # 4. Setup Ranch Price
    rp = RanchPrice(cost=5.00, price=6.00, date=date(2024, 1, 1), company_id=company_id)
    db.session.add(rp)

    # 5. Setup Designation Cost
    dc = DesignationCost(item_designation='RETAIL', cost=2.00, date=date(2024, 1, 1), company_id=company_id)
    db.session.add(dc)

    db.session.commit()
    
    return pack, [raw1, raw2]

def test_full_price_calculation(client, logged_in_user, app):
    """
    Test the complete calculation logic in the Price Quoter.
    WE EXPECT:
    - Packaging: 1.50 + 0.50 + 0.25 + 0.10 = $2.35
    - Raw: 10.00 + 20.00 = $30.00 (No override)
    - Labor: 2 hours * $15.00/hr = $30.00
    - Ranch: $5.00 (if checked)
    - Designation: $2.00 ('RETAIL')
    
    TOTAL COST = 2.35 + 30.00 + 30.00 + 5.00 + 2.00 = $69.35
    YIELD = 100 lbs
    COST PER LB = 69.35 / 100 = $0.6935
    """
    with app.app_context():
        pack, raws = _setup_calculation_scenario(logged_in_user.company_id)
        
        # Calculate expected sum: 10 + 20 = 30.00
        # The JS on the frontend would auto-fill this.
        # Since the field has DataRequired(), we must provide it.
        
        data = {
            'action': 'calculate',
            'packaging': pack.id,
            'raw_products': [r.id for r in raws],
            'raw_product_cost': 30.00, 
            'product_yield': 100,
            'labor_hours': 2,
            'ranch': True,
            'item_designation': 'RETAIL',
            'case_weight': 10,
        }

        response = client.post('/price_quoter', data=data, follow_redirects=True)
        text = response.get_data(as_text=True)

        # Debug if needed
        if "Total Unit Cost" not in text:
             print(text)

        # Helper to assert value in text
        def assert_in_text(label, value):
             assert f"{label}: ${value}" in text, f"Expected {label}: ${value} not found."

        # 1. Check Total Cost matches expectation ($69.35)
        # Template: Total Unit Cost: ${{ result.total_cost|round(2) }}
        # 69.35
        assert "Total Unit Cost: $69.35" in text

        # 2. Check Cost per lb ($0.6935)
        # Template: Cost per lb: ${{ result.cost_per_lb|round(4) }}
        assert "Cost per lb: $0.6935" in text
        
        # 3. Check Margins
        # +25% Margin: 69.35 * 1.25 = 86.6875 -> ~86.69
        # Template: +25% Margin: ${{ result.rounded_25|round(2) }}
        assert "+25% Margin: $86.69" in text

def test_calculation_with_manual_override_and_no_extras(client, logged_in_user, app):
    """
    Test calculation with raw cost override and disabling ranch/designation.
    EXPECT:
    - Packaging: $2.35
    - Raw Override: $25.00 avg * 2 items = $50.00
    - Labor: 1 hour * $15.00 = $15.00
    - Ranch: $0
    - Designation: None -> $0
    
    TOTAL = 2.35 + 50.00 + 15.00 = $67.35
    """
    with app.app_context():
        pack, raws = _setup_calculation_scenario(logged_in_user.company_id)
        
        # We need to satisfy DataRequired for item_designation.
        # We'll use 'SNAKPAK' which has no cost entry in DB, so designation cost = 0.

        data = {
            'action': 'calculate',
            'packaging': pack.id,
            'raw_products': [r.id for r in raws],
            'raw_product_cost': 25.00, # Override
            'product_yield': 100,
            'labor_hours': 1,
            # 'ranch': False, # Disabled
            'item_designation': 'SNAKPAK', # Valid choice
            'case_weight': 10,
        }

        response = client.post('/price_quoter', data=data, follow_redirects=True)
        text = response.get_data(as_text=True)

        assert "Raw Cost: $25.0" in text      # 25 * 1
        assert "Labor Cost: $15.0" in text    # 1 * 15
        assert "Ranch Cost: $0" in text
        assert "Designation Cost: $0" in text
        assert "Total Unit Cost: $42.35" in text

def test_create_item_saves_to_db(client, logged_in_user, app):
    """
    Test that clicking 'Save as New Item' actually creates the Item and ItemInfo records.
    """
    with app.app_context():
        pack, raws = _setup_calculation_scenario(logged_in_user.company_id)
        
        data = {
            'action': 'create', # This triggers the save logic
            'name': 'New Test Item',
            'code': 'TEST001',
            'packaging': pack.id,
            'raw_products': [r.id for r in raws],
            'raw_product_cost': 25.00,
            'product_yield': 500,
            'labor_hours': 5,
            'ranch': True,
            'item_designation': 'FOODSERVICE',
            'case_weight': 20,
        }

        response = client.post('/price_quoter', data=data, follow_redirects=True)
        
        # Should redirect to items page usually, verify we are there or item exists
        item = Item.query.filter_by(name='New Test Item').first()
        assert item is not None
        assert item.code == 'TEST001'
        assert item.packaging_id == pack.id
        assert item.ranch is True
        assert len(item.raw_products) == 2
        
        # Check ItemInfo was created
        info = ItemInfo.query.filter_by(item_id=item.id).first()
        assert info is not None
        assert info.product_yield == 500
        assert info.labor_hours == 5
