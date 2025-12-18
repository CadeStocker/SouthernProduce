import pytest
from flask import url_for
from datetime import date
from producepricer import db
from producepricer.models import LaborCost, Item, ItemTotalCost, Packaging, UnitOfWeight, ItemDesignation

class TestLaborCost:
    def test_add_labor_cost(self, client, app, logged_in_user):
        """Test adding a new labor cost."""
        url = url_for('main.add_labor_cost')
        
        # GET request
        response = client.get(url)
        assert response.status_code == 200
        assert b"Add Labor Cost" in response.data
        
        # POST request
        data = {
            'cost': 25.50,
            'date': date.today().isoformat()
        }
        response = client.post(url, data=data, follow_redirects=True)
        assert response.status_code == 200
        assert b"Labor cost added successfully!" in response.data
        
        # Verify in DB
        with app.app_context():
            lc = LaborCost.query.filter_by(company_id=logged_in_user.company_id, labor_cost=25.50).first()
            assert lc is not None

    def test_delete_labor_cost(self, client, app, logged_in_user):
        """Test deleting a labor cost."""
        with app.app_context():
            lc = LaborCost(
                labor_cost=20.0,
                date=date.today(),
                company_id=logged_in_user.company_id
            )
            db.session.add(lc)
            db.session.commit()
            lc_id = lc.id
            
        url = url_for('main.delete_labor_cost', cost_id=lc_id)
        response = client.post(url, follow_redirects=True)
        
        assert response.status_code == 200
        assert b"Labor cost has been deleted successfully" in response.data
        
        # Verify deletion
        with app.app_context():
            lc = db.session.get(LaborCost, lc_id)
            assert lc is None

    def test_labor_cost_update_triggers_item_cost_update(self, client, app, logged_in_user):
        """Test that adding a labor cost updates item costs."""
        with app.app_context():
            # Setup item
            packaging = Packaging(packaging_type="Box", company_id=logged_in_user.company_id)
            db.session.add(packaging)
            db.session.commit()
            
            item = Item(
                name="Labor Test Item",
                code="LBR-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging.id,
                company_id=logged_in_user.company_id,
                item_designation=ItemDesignation.RETAIL,
                case_weight=10.0
            )
            db.session.add(item)
            db.session.commit()
            
            # Initial cost calculation (needs at least one labor cost to work properly usually, 
            # but let's see if adding a new one triggers update)
            # We'll add an initial labor cost
            lc1 = LaborCost(labor_cost=10.0, date=date(2024, 1, 1), company_id=logged_in_user.company_id)
            db.session.add(lc1)
            db.session.commit()
            
            # Create an item info with labor hours
            from producepricer.models import ItemInfo
            info = ItemInfo(
                product_yield=1.0,
                item_id=item.id,
                labor_hours=2.0, # 2 hours * $10 = $20 labor cost
                date=date.today(),
                company_id=logged_in_user.company_id
            )
            db.session.add(info)
            db.session.commit()
            
            item_id = item.id
            
            # Manually trigger cost update or create initial cost
            # The route logic usually handles this, but let's just check if the NEW labor cost updates it
            
        # Add new labor cost via route
        url = url_for('main.add_labor_cost')
        data = {
            'cost': 20.0, # New cost: 2 hours * $20 = $40 labor cost
            'date': date.today().isoformat()
        }
        client.post(url, data=data, follow_redirects=True)
        
        with app.app_context():
            # Check most recent item cost
            cost = ItemTotalCost.query.filter_by(item_id=item_id).order_by(ItemTotalCost.id.desc()).first()
            assert cost is not None
            # Labor cost should be 40.0 (2.0 hours * 20.0/hr)
            assert cost.labor_cost == 40.0
