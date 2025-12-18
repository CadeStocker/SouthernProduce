import pytest
from flask import url_for
from producepricer import db
from producepricer.models import RawProduct, Item, UnitOfWeight, ItemDesignation, Packaging, LaborCost, ItemTotalCost
from datetime import date

class TestPagination:
    @pytest.fixture
    def pagination_data(self, app, logged_in_user):
        """Create enough data to trigger pagination (more than 15 items)."""
        with app.app_context():
            # Create 20 raw products
            for i in range(20):
                rp = RawProduct(
                    name=f"Raw Product {i:02d}",
                    company_id=logged_in_user.company_id
                )
                db.session.add(rp)
            
            # Create packaging (needed for items)
            packaging = Packaging(
                packaging_type="Test Box",
                company_id=logged_in_user.company_id
            )
            db.session.add(packaging)
            db.session.commit() # Commit to get IDs
            
            # Create labor cost (needed for item cost calculation)
            labor = LaborCost(
                labor_cost=15.0,
                date=date.today(),
                company_id=logged_in_user.company_id
            )
            db.session.add(labor)

            # Create 20 items
            for i in range(20):
                item = Item(
                    name=f"Item {i:02d}",
                    code=f"ITM-{i:02d}",
                    unit_of_weight=UnitOfWeight.POUND,
                    packaging_id=packaging.id,
                    company_id=logged_in_user.company_id,
                    item_designation=ItemDesignation.RETAIL,
                    case_weight=10.0
                )
                db.session.add(item)
                db.session.commit() # Commit to get item ID
                
                # Add a cost so it shows up nicely in price page
                cost = ItemTotalCost(
                    item_id=item.id,
                    total_cost=10.0,
                    date=date.today(),
                    company_id=logged_in_user.company_id,
                    labor_cost=1.0,
                    designation_cost=1.0,
                    packaging_cost=1.0,
                    ranch_cost=0.0,
                    raw_product_cost=7.0
                )
                db.session.add(cost)
            
            db.session.commit()

    def test_raw_product_pagination(self, client, pagination_data):
        """Test pagination on raw product page."""
        # Default view (show all)
        response = client.get(url_for('main.raw_product'))
        assert response.status_code == 200
        assert b"Raw Product 00" in response.data
        assert b"Raw Product 19" in response.data
        # Should NOT show pagination controls when showing all
        assert b"Use Pagination" in response.data
        
        # Paginated view
        response = client.get(url_for('main.raw_product', paginate=1))
        assert response.status_code == 200
        # Should show first page (15 items)
        assert b"Raw Product 00" in response.data
        # Should NOT show the last items (sorted by name)
        # Raw Product 19 might be on page 2
        
        # Check for pagination controls
        assert b"Show All" in response.data
        assert b"Next" in response.data

        # Check page 2
        response = client.get(url_for('main.raw_product', paginate=1, page=2))
        assert response.status_code == 200
        assert b"Raw Product 19" in response.data

    def test_price_page_pagination(self, client, pagination_data):
        """Test pagination on price page."""
        # Default view (show all)
        response = client.get(url_for('main.price'))
        assert response.status_code == 200
        assert b"Item 00" in response.data
        assert b"Item 19" in response.data
        # Should NOT show pagination controls when showing all
        assert b"Use Pagination" in response.data
        
        # Paginated view
        response = client.get(url_for('main.price', paginate=1))
        assert response.status_code == 200
        # Should show first page
        assert b"Item 00" in response.data
        
        # Check for pagination controls
        assert b"Show All" in response.data
        assert b"Next" in response.data

        # Check page 2
        response = client.get(url_for('main.price', paginate=1, page=2))
        assert response.status_code == 200
        assert b"Item 19" in response.data
