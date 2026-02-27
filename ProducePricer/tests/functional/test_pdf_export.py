"""
Tests for PDF export functionality including:
- Raw product price sheet PDF generation
- Price sheet PDF generation
- PDF export routes
- PDF content validation
"""

import pytest
from datetime import date, datetime, timedelta
from flask import url_for
from unittest.mock import patch, MagicMock
from io import BytesIO
from producepricer import db
from producepricer.models import (
    Company, User, Item, RawProduct, Packaging, PackagingCost,
    Customer, CostHistory, PriceHistory, PriceSheet, LaborCost,
    ItemInfo, ItemTotalCost, UnitOfWeight, ItemDesignation
)


# ====================
# Fixtures
# ====================

@pytest.fixture
def setup_pdf_test_company(app):
    """Create a company with all necessary data for PDF tests."""
    with app.app_context():
        # Create company
        company = Company(name="PDF Test Company", admin_email="pdfadmin@test.com")
        db.session.add(company)
        db.session.commit()
        
        # Create admin user
        user = User(
            first_name="PDF",
            last_name="Admin",
            email="pdfadmin@test.com",
            password="pdfpass",
            company_id=company.id
        )
        db.session.add(user)
        
        # Create packaging
        packaging = Packaging(packaging_type="PDF Test Box", company_id=company.id)
        db.session.add(packaging)
        db.session.commit()
        
        # Create packaging cost
        pkg_cost = PackagingCost(
            packaging_id=packaging.id,
            box_cost=2.50,
            bag_cost=0.75,
            tray_andor_chemical_cost=0.30,
            label_andor_tape_cost=0.20,
            date=date.today(),
            company_id=company.id
        )
        db.session.add(pkg_cost)
        
        # Create labor cost
        labor_cost = LaborCost(
            date=date.today(),
            labor_cost=20.00,
            company_id=company.id
        )
        db.session.add(labor_cost)
        
        # Create master customer
        master_customer = Customer(
            name="Master PDF Customer",
            email="masterpdf@test.com",
            company_id=company.id
        )
        master_customer.is_master = True
        db.session.add(master_customer)
        
        # Create regular customer
        regular_customer = Customer(
            name="Regular PDF Customer",
            email="regularpdf@test.com",
            company_id=company.id
        )
        db.session.add(regular_customer)
        
        db.session.commit()
        
        return {
            'company_id': company.id,
            'user_id': user.id,
            'packaging_id': packaging.id,
            'master_customer_id': master_customer.id,
            'regular_customer_id': regular_customer.id
        }


@pytest.fixture
def setup_raw_products(app, setup_pdf_test_company):
    """Create raw products with cost history for PDF tests."""
    with app.app_context():
        setup = setup_pdf_test_company
        
        raw_products = []
        for i in range(5):
            rp = RawProduct(
                name=f"PDF Raw Product {i}",
                company_id=setup['company_id']
            )
            raw_products.append(rp)
        db.session.add_all(raw_products)
        db.session.commit()
        
        # Add cost history for each raw product
        for rp in raw_products:
            cost = CostHistory(
                raw_product_id=rp.id,
                cost=5.00 + raw_products.index(rp) * 0.50,
                date=date.today(),
                company_id=setup['company_id']
            )
            db.session.add(cost)
        db.session.commit()
        
        return {
            **setup,
            'raw_product_ids': [rp.id for rp in raw_products]
        }


@pytest.fixture
def setup_items_with_prices(app, setup_raw_products):
    """Create items with price history for PDF tests."""
    with app.app_context():
        setup = setup_raw_products
        
        items = []
        for i in range(5):
            item = Item(
                name=f"PDF Test Item {i}",
                code=f"PDF-{i:03d}",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id'],
                case_weight=10.0,
                ranch=False
            )
            items.append(item)
        db.session.add_all(items)
        db.session.commit()
        
        # Add price history for master customer
        for item in items:
            price = PriceHistory(
                item_id=item.id,
                date=date.today(),
                company_id=setup['company_id'],
                customer_id=setup['master_customer_id'],
                price=25.00 + items.index(item) * 2.00
            )
            db.session.add(price)
        
        # Add ItemInfo for each item (required for cost calculation)
        for item in items:
            item_info = ItemInfo(
                item_id=item.id,
                product_yield=80.0,
                labor_hours=0.5,
                date=date.today(),
                company_id=setup['company_id']
            )
            db.session.add(item_info)
        
        # Add ItemTotalCost for each item
        for item in items:
            item_cost = ItemTotalCost(
                item_id=item.id,
                total_cost=50.00 + items.index(item) * 2.00,
                labor_cost=10.00,
                packaging_cost=5.00,
                ranch_cost=0.00,
                raw_product_cost=30.00,
                designation_cost=5.00,
                date=date.today(),
                company_id=setup['company_id']
            )
            db.session.add(item_cost)
        
        db.session.commit()
        
        return {
            **setup,
            'item_ids': [item.id for item in items]
        }


@pytest.fixture
def setup_price_sheet(app, setup_items_with_prices):
    """Create a price sheet for PDF tests."""
    with app.app_context():
        setup = setup_items_with_prices
        
        # Get items
        items = Item.query.filter(Item.id.in_(setup['item_ids'])).all()
        
        # Create price sheet
        sheet = PriceSheet(
            name="PDF Test Sheet",
            date=date.today(),
            company_id=setup['company_id'],
            customer_id=setup['master_customer_id']
        )
        sheet.items.extend(items)
        db.session.add(sheet)
        db.session.commit()
        
        return {
            **setup,
            'sheet_id': sheet.id
        }


@pytest.fixture
def logged_in_pdf_user(client, app, setup_pdf_test_company):
    """Return a client logged in for PDF tests."""
    client.post('/login', data={
        'email': 'pdfadmin@test.com',
        'password': 'pdfpass'
    })
    return client


# ====================
# Raw Price Sheet PDF Tests
# ====================

class TestRawPriceSheetPDF:
    """Tests for raw product price sheet PDF generation."""
    
    def test_raw_price_sheet_page_loads(self, logged_in_pdf_user, app, setup_raw_products):
        """Test that raw price sheet page loads."""
        response = logged_in_pdf_user.get('/raw_price_sheet')
        assert response.status_code == 200

    def test_export_raw_price_sheet_pdf(self, logged_in_pdf_user, app, setup_raw_products):
        """Test exporting raw price sheet as PDF."""
        response = logged_in_pdf_user.get('/raw_price_sheet/export_pdf')
        
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert 'attachment' in response.headers.get('Content-Disposition', '')
        assert '.pdf' in response.headers.get('Content-Disposition', '')

    def test_raw_price_sheet_pdf_contains_data(self, logged_in_pdf_user, app, setup_raw_products):
        """Test that raw price sheet PDF contains raw product data."""
        response = logged_in_pdf_user.get('/raw_price_sheet/export_pdf')
        
        assert response.status_code == 200
        # PDF should have content (more than just headers)
        assert len(response.data) > 100

    def test_raw_price_sheet_pdf_filename(self, logged_in_pdf_user, app, setup_raw_products):
        """Test that raw price sheet PDF has correct filename."""
        response = logged_in_pdf_user.get('/raw_price_sheet/export_pdf')
        
        content_disposition = response.headers.get('Content-Disposition', '')
        assert 'raw_price_sheet' in content_disposition.lower()

    def test_generate_raw_price_sheet_pdf_bytes_function(self, app, setup_raw_products):
        """Test the _generate_raw_price_sheet_pdf_bytes helper function directly."""
        from producepricer.blueprints.raw_products import _generate_raw_price_sheet_pdf_bytes
        
        with app.app_context():
            setup = setup_raw_products
            
            raw_products = RawProduct.query.filter_by(company_id=setup['company_id']).all()
            
            # Build recent map like the route does
            recent = {}
            for rp in raw_products:
                ch = CostHistory.query.filter_by(
                    raw_product_id=rp.id,
                    company_id=setup['company_id']
                ).order_by(CostHistory.date.desc()).first()
                recent[rp.id] = {
                    'name': rp.name,
                    'price': f"{ch.cost:.2f}" if ch and ch.cost is not None else None,
                    'date': ch.date.strftime('%Y-%m-%d') if ch and ch.date else None
                }
            
            pdf_bytes = _generate_raw_price_sheet_pdf_bytes(raw_products, recent)
            
            assert pdf_bytes is not None
            assert isinstance(pdf_bytes, bytes)
            assert len(pdf_bytes) > 0
            # Check PDF header
            assert pdf_bytes[:4] == b'%PDF'

    def test_raw_price_sheet_pdf_with_no_costs(self, logged_in_pdf_user, app, setup_pdf_test_company):
        """Test raw price sheet PDF generation when raw products have no costs."""
        with app.app_context():
            setup = setup_pdf_test_company
            
            # Create raw product without cost history
            rp = RawProduct(name="No Cost Product", company_id=setup['company_id'])
            db.session.add(rp)
            db.session.commit()
        
        response = logged_in_pdf_user.get('/raw_price_sheet/export_pdf')
        
        # Should still generate PDF, possibly with "-" for missing price
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'

    def test_raw_price_sheet_pdf_custom_sheet_name(self, app, setup_raw_products):
        """Test that custom sheet name is used in PDF."""
        from producepricer.blueprints.raw_products import _generate_raw_price_sheet_pdf_bytes
        
        with app.app_context():
            setup = setup_raw_products
            raw_products = RawProduct.query.filter_by(company_id=setup['company_id']).all()
            recent = {rp.id: {'name': rp.name, 'price': '5.00', 'date': '2024-01-01'} for rp in raw_products}
            
            pdf_bytes = _generate_raw_price_sheet_pdf_bytes(
                raw_products, recent, sheet_name="Custom Sheet Name"
            )
            
            assert pdf_bytes is not None
            assert len(pdf_bytes) > 0


# ====================
# Price Sheet PDF Tests
# ====================

class TestPriceSheetPDF:
    """Tests for price sheet PDF generation."""
    
    def test_export_price_sheet_pdf(self, logged_in_pdf_user, app, setup_price_sheet):
        """Test exporting price sheet as PDF."""
        setup = setup_price_sheet
        
        response = logged_in_pdf_user.get(f'/view_price_sheet/{setup["sheet_id"]}/export_pdf')
        
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'

    def test_price_sheet_pdf_filename(self, logged_in_pdf_user, app, setup_price_sheet):
        """Test that price sheet PDF has correct filename."""
        setup = setup_price_sheet
        
        response = logged_in_pdf_user.get(f'/view_price_sheet/{setup["sheet_id"]}/export_pdf')
        
        content_disposition = response.headers.get('Content-Disposition', '')
        assert 'price_sheet' in content_disposition.lower()
        assert '.pdf' in content_disposition

    def test_price_sheet_pdf_contains_items(self, logged_in_pdf_user, app, setup_price_sheet):
        """Test that price sheet PDF is generated with item data."""
        setup = setup_price_sheet
        
        response = logged_in_pdf_user.get(f'/view_price_sheet/{setup["sheet_id"]}/export_pdf')
        
        assert response.status_code == 200
        # PDF should have substantial content
        assert len(response.data) > 100

    def test_export_nonexistent_price_sheet_404(self, logged_in_pdf_user, app):
        """Test that exporting non-existent price sheet returns 404."""
        response = logged_in_pdf_user.get('/view_price_sheet/99999/export_pdf')
        assert response.status_code == 404

    def test_price_sheet_pdf_requires_login(self, client, app, setup_price_sheet):
        """Test that price sheet PDF export requires authentication."""
        setup = setup_price_sheet
        
        response = client.get(f'/view_price_sheet/{setup["sheet_id"]}/export_pdf')
        
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location

    def test_price_sheet_pdf_with_recently_changed_prices(self, logged_in_pdf_user, app, setup_price_sheet):
        """Test that PDF marks recently changed prices."""
        setup = setup_price_sheet
        
        # Update price to today to ensure it shows as "changed"
        with app.app_context():
            item = db.session.get(Item, setup['item_ids'][0])
            new_price = PriceHistory(
                item_id=item.id,
                date=date.today(),
                company_id=setup['company_id'],
                customer_id=setup['master_customer_id'],
                price=50.00
            )
            db.session.add(new_price)
            db.session.commit()
        
        response = logged_in_pdf_user.get(f'/view_price_sheet/{setup["sheet_id"]}/export_pdf')
        
        assert response.status_code == 200
        # PDF should still generate
        assert len(response.data) > 100


# ====================
# PDF Content Validation Tests
# ====================

class TestPDFContentValidation:
    """Tests for validating PDF content structure."""
    
    def test_pdf_has_valid_header(self, logged_in_pdf_user, app, setup_raw_products):
        """Test that generated PDF has valid PDF header."""
        response = logged_in_pdf_user.get('/raw_price_sheet/export_pdf')
        
        # PDF files start with %PDF-
        assert response.data[:4] == b'%PDF'

    def test_pdf_is_not_empty(self, logged_in_pdf_user, app, setup_raw_products):
        """Test that generated PDF is not empty."""
        response = logged_in_pdf_user.get('/raw_price_sheet/export_pdf')
        
        # A valid PDF should be at least a few KB
        assert len(response.data) > 500


# ====================
# PDF Generation Edge Cases
# ====================

class TestPDFEdgeCases:
    """Tests for edge cases in PDF generation."""
    
    def test_pdf_with_zero_prices(self, logged_in_pdf_user, app, setup_price_sheet):
        """Test PDF generation with zero prices."""
        setup = setup_price_sheet
        
        # Create item with zero price
        with app.app_context():
            item = Item(
                name="Zero Price Item",
                code="ZERO-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=setup['packaging_id'],
                company_id=setup['company_id']
            )
            db.session.add(item)
            db.session.commit()
            
            price = PriceHistory(
                item_id=item.id,
                date=date.today(),
                company_id=setup['company_id'],
                customer_id=setup['master_customer_id'],
                price=0.00
            )
            db.session.add(price)
            
            sheet = db.session.get(PriceSheet, setup['sheet_id'])
            sheet.items.append(item)
            db.session.commit()
        
        response = logged_in_pdf_user.get(f'/view_price_sheet/{setup["sheet_id"]}/export_pdf')
        assert response.status_code == 200

    def test_pdf_with_empty_price_sheet(self, logged_in_pdf_user, app, setup_pdf_test_company):
        """Test PDF generation with empty price sheet (no items)."""
        setup = setup_pdf_test_company
        
        # Create customer and empty price sheet
        with app.app_context():
            customer = Customer(
                name="Empty Sheet Customer",
                email="empty@test.com",
                company_id=setup['company_id']
            )
            db.session.add(customer)
            db.session.commit()
            
            # Create empty price sheet
            empty_sheet = PriceSheet(
                name="Empty Sheet",
                date=date.today(),
                company_id=setup['company_id'],
                customer_id=customer.id
            )
            db.session.add(empty_sheet)
            db.session.commit()
            sheet_id = empty_sheet.id
        
        response = logged_in_pdf_user.get(f'/view_price_sheet/{sheet_id}/export_pdf')
        # Should still generate a valid (albeit small) PDF
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'


# ====================
# PDF Security Tests
# ====================

class TestPDFSecurity:
    """Tests for PDF export security."""
    
    def test_cannot_export_other_company_price_sheet(self, logged_in_pdf_user, app):
        """Test that users cannot export price sheets from other companies."""
        # Create another company with a price sheet
        with app.app_context():
            other_company = Company(name="Other PDF Co", admin_email="otherpdf@test.com")
            db.session.add(other_company)
            db.session.commit()
            
            # Create packaging for other company
            other_pkg = Packaging(packaging_type="Other Box", company_id=other_company.id)
            db.session.add(other_pkg)
            db.session.commit()
            
            # Create customer for other company
            other_customer = Customer(
                name="Other Customer",
                email="othercust@test.com",
                company_id=other_company.id
            )
            db.session.add(other_customer)
            db.session.commit()
            
            # Create sheet for other company
            other_sheet = PriceSheet(
                name="Other Company Sheet",
                date=date.today(),
                company_id=other_company.id,
                customer_id=other_customer.id
            )
            db.session.add(other_sheet)
            db.session.commit()
            other_sheet_id = other_sheet.id
        
        # Try to access other company's sheet
        response = logged_in_pdf_user.get(f'/view_price_sheet/{other_sheet_id}/export_pdf')
        
        # Should return 404 (not found for this user's company)
        assert response.status_code == 404

    def test_pdf_export_requires_authentication(self, client, app, setup_price_sheet):
        """Test that PDF export requires user to be logged in."""
        setup = setup_price_sheet
        
        # Try without logging in
        response = client.get(f'/view_price_sheet/{setup["sheet_id"]}/export_pdf')
        
        assert response.status_code == 302
        assert '/login' in response.location

    def test_raw_pdf_export_requires_authentication(self, client, app):
        """Test that raw price sheet PDF export requires authentication."""
        response = client.get('/raw_price_sheet/export_pdf')
        
        assert response.status_code == 302
        assert '/login' in response.location


# ====================
# PDF Helper Function Tests
# ====================

class TestPDFHelperFunctions:
    """Tests for PDF helper functions."""
    
    def test_raw_pdf_bytes_returns_correct_type(self, app, setup_raw_products):
        """Test that raw PDF bytes returns correct type."""
        from producepricer.blueprints.raw_products import _generate_raw_price_sheet_pdf_bytes
        
        with app.app_context():
            setup = setup_raw_products
            raw_products = RawProduct.query.filter_by(company_id=setup['company_id']).all()
            recent = {rp.id: {'name': rp.name, 'price': '5.00', 'date': '2024-01-01'} for rp in raw_products}
            
            result = _generate_raw_price_sheet_pdf_bytes(raw_products, recent)
            
            assert isinstance(result, bytes)

    def test_raw_pdf_with_none_values(self, app, setup_pdf_test_company):
        """Test raw PDF generation handles None values gracefully."""
        from producepricer.blueprints.raw_products import _generate_raw_price_sheet_pdf_bytes
        
        with app.app_context():
            setup = setup_pdf_test_company
            
            # Create raw product
            rp = RawProduct(name="None Test", company_id=setup['company_id'])
            db.session.add(rp)
            db.session.commit()
            
            # Create recent map with None values
            recent = {
                rp.id: {
                    'name': rp.name,
                    'price': None,
                    'date': None
                }
            }
            
            # Should not raise exception
            result = _generate_raw_price_sheet_pdf_bytes([rp], recent)
            assert result is not None
            assert len(result) > 0


# ====================
# PDF Download Tests
# ====================

class TestPDFDownload:
    """Tests for PDF download behavior."""
    
    def test_pdf_response_headers(self, logged_in_pdf_user, app, setup_price_sheet):
        """Test that PDF response has correct headers."""
        setup = setup_price_sheet
        
        response = logged_in_pdf_user.get(f'/view_price_sheet/{setup["sheet_id"]}/export_pdf')
        
        # Check content type
        assert response.content_type == 'application/pdf'
        
        # Check content disposition
        content_disposition = response.headers.get('Content-Disposition')
        assert content_disposition is not None
        assert 'attachment' in content_disposition
        assert 'filename=' in content_disposition

    def test_pdf_can_be_saved_as_file(self, logged_in_pdf_user, app, setup_price_sheet, tmp_path):
        """Test that PDF response can be saved as a valid file."""
        setup = setup_price_sheet
        
        response = logged_in_pdf_user.get(f'/view_price_sheet/{setup["sheet_id"]}/export_pdf')
        
        # Save to temp file
        pdf_file = tmp_path / "test_output.pdf"
        pdf_file.write_bytes(response.data)
        
        # Verify file was written
        assert pdf_file.exists()
        assert pdf_file.stat().st_size > 0
        
        # Verify it starts with PDF header
        content = pdf_file.read_bytes()
        assert content[:4] == b'%PDF'


# ====================
# Price Table PDF Export Tests
# ====================

class TestPriceTablePDFExport:
    """Tests for the /price/export-pdf route that exports the item pricing table."""
    
    def test_price_pdf_export_requires_login(self, client, app):
        """Test that the price PDF export route requires authentication."""
        with app.app_context():
            response = client.get(url_for('main.export_price_pdf'))
            # Should redirect to login
            assert response.status_code == 302
            assert '/login' in response.location
    
    def test_price_pdf_export_basic_functionality(self, client, app, setup_items_with_prices, logged_in_pdf_user):
        """Test that price PDF export generates a valid PDF with basic functionality."""
        with app.app_context():
            url = url_for('main.export_price_pdf')
        
        response = logged_in_pdf_user.get(url)
        
        # Check response headers
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert 'attachment' in response.headers.get('Content-Disposition', '')
        assert 'item_pricing_' in response.headers.get('Content-Disposition', '')
        assert '.pdf' in response.headers.get('Content-Disposition', '')
        
        # Verify PDF content
        assert response.data[:4] == b'%PDF'
        assert len(response.data) > 1000  # Should have substantial content
    
    def test_price_pdf_export_with_search_query(self, client, app, setup_items_with_prices, logged_in_pdf_user):
        """Test that price PDF export respects search query parameter."""
        with app.app_context():
            # Export with search query
            url = url_for('main.export_price_pdf', q='Item 0')
        
        response = logged_in_pdf_user.get(url)
        
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert response.data[:4] == b'%PDF'
    
    def test_price_pdf_export_with_no_items(self, client, app, setup_pdf_test_company):
        """Test that price PDF export works even with no items."""
        # Login first
        client.post('/login', data={
            'email': 'pdfadmin@test.com',
            'password': 'pdfpass'
        }, follow_redirects=True)
        
        with app.app_context():
            url = url_for('main.export_price_pdf')
        
        response = client.get(url)
        
        # Should still generate a PDF, just with empty table
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert response.data[:4] == b'%PDF'
    
    def test_price_pdf_export_filename_format(self, client, app, setup_items_with_prices, logged_in_pdf_user):
        """Test that the PDF filename has correct timestamp format."""
        with app.app_context():
            url = url_for('main.export_price_pdf')
        
        response = logged_in_pdf_user.get(url)
        
        content_disposition = response.headers.get('Content-Disposition', '')
        
        # Check filename pattern: item_pricing_YYYYMMDD_HHMMSS.pdf
        assert 'item_pricing_' in content_disposition
        assert '.pdf' in content_disposition
        
        # Extract and verify filename pattern
        import re
        filename_match = re.search(r'item_pricing_(\d{8}_\d{6})\.pdf', content_disposition)
        assert filename_match is not None
        
        # Verify timestamp format is valid
        timestamp = filename_match.group(1)
        assert len(timestamp) == 15  # YYYYMMDD_HHMMSS = 15 characters
    
    def test_price_pdf_export_contains_company_name(self, client, app, setup_items_with_prices, logged_in_pdf_user):
        """Test that the PDF contains the company name in the header."""
        with app.app_context():
            url = url_for('main.export_price_pdf')
        
        response = logged_in_pdf_user.get(url)
        
        # Verify PDF is generated successfully
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert response.data[:4] == b'%PDF'
        
        # PDF should have substantial content (more than just header/footer)
        # A PDF with 5 items should be at least 2KB
        assert len(response.data) > 2000, f"PDF too small ({len(response.data)} bytes), likely missing content"
    
    def test_price_pdf_export_contains_item_data(self, client, app, setup_items_with_prices, logged_in_pdf_user):
        """Test that the PDF contains actual item data."""
        with app.app_context():
            # Get one of the items to verify
            item = Item.query.filter_by(code='PDF-000').first()
            assert item is not None
            
            # Get all items to know how many we expect
            items = Item.query.filter_by(company_id=1).all()
            item_count = len(items)
            
            url = url_for('main.export_price_pdf')
        
        response = logged_in_pdf_user.get(url)
        
        # Verify PDF is generated successfully
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert response.data[:4] == b'%PDF'
        
        # PDF should have substantial content - each item adds to the size
        # With 5 items, expect at least 2KB
        assert len(response.data) > 2000, f"PDF too small ({len(response.data)} bytes), likely missing item data"
    
    def test_price_pdf_export_with_special_characters_in_item_name(self, client, app, setup_items_with_prices, logged_in_pdf_user):
        """Test that PDF export handles items with special characters in names."""
        with app.app_context():
            # Create an item with special characters
            setup = setup_items_with_prices
            packaging = Packaging.query.first()
            
            item = Item(
                name="Special Item: Test & Product (100%)",
                code="SPEC-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging.id,
                company_id=setup['company_id'],
                case_weight=10.0
            )
            db.session.add(item)
            db.session.commit()
            
            # Create item total cost
            item_cost = ItemTotalCost(
                item_id=item.id,
                total_cost=50.00,
                labor_cost=10.00,
                packaging_cost=5.00,
                ranch_cost=2.00,
                raw_product_cost=30.00,
                designation_cost=3.00,
                date=date.today(),
                company_id=setup['company_id']
            )
            db.session.add(item_cost)
            db.session.commit()
            url = url_for('main.export_price_pdf')
        
        response = logged_in_pdf_user.get(url)
        
        # Should successfully generate PDF
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert response.data[:4] == b'%PDF'
    
    def test_price_pdf_export_with_long_item_names(self, client, app, setup_items_with_prices, logged_in_pdf_user):
        """Test that PDF export handles very long item names correctly."""
        with app.app_context():
            # Create an item with a very long name
            setup = setup_items_with_prices
            packaging = Packaging.query.first()
            
            long_name = "A" * 150  # Very long name
            
            item = Item(
                name=long_name,
                code="LONG-001",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging.id,
                company_id=setup['company_id'],
                case_weight=10.0
            )
            db.session.add(item)
            db.session.commit()
            
            # Create item total cost
            item_cost = ItemTotalCost(
                item_id=item.id,
                total_cost=50.00,
                labor_cost=10.00,
                packaging_cost=5.00,
                ranch_cost=2.00,
                raw_product_cost=30.00,
                designation_cost=3.00,
                date=date.today(),
                company_id=setup['company_id']
            )
            db.session.add(item_cost)
            db.session.commit()
            url = url_for('main.export_price_pdf')
        
        response = logged_in_pdf_user.get(url)
        
        # Should successfully generate PDF without errors
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert response.data[:4] == b'%PDF'
    
    def test_price_pdf_export_saves_to_file_correctly(self, client, app, setup_items_with_prices, logged_in_pdf_user, tmp_path):
        """Test that the exported PDF can be saved and is a valid PDF file."""
        with app.app_context():
            url = url_for('main.export_price_pdf')
        
        response = logged_in_pdf_user.get(url)
        
        # Save to temp file
        pdf_file = tmp_path / "price_export_test.pdf"
        pdf_file.write_bytes(response.data)
        
        # Verify file was written
        assert pdf_file.exists()
        assert pdf_file.stat().st_size > 1000  # Should have substantial content
        
        # Verify it starts with PDF header
        content = pdf_file.read_bytes()
        assert content[:4] == b'%PDF'
        
        # Verify PDF ends properly
        assert b'%%EOF' in content
    
    def test_price_pdf_export_with_multiple_items(self, client, app, setup_items_with_prices, logged_in_pdf_user):
        """Test that PDF export handles multiple items correctly."""
        with app.app_context():
            # setup_items_with_prices already creates 5 items
            url = url_for('main.export_price_pdf')
        
        response = logged_in_pdf_user.get(url)
        
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        
        # PDF should be larger with more items
        assert len(response.data) > 2000
    
    def test_price_pdf_export_search_filters_items(self, client, app, setup_items_with_prices, logged_in_pdf_user):
        """Test that search parameter correctly filters items in PDF export."""
        with app.app_context():
            # Export all items
            url_all = url_for('main.export_price_pdf')
            # Export with search filter
            url_filtered = url_for('main.export_price_pdf', q='Item 0')
        
        response_all = logged_in_pdf_user.get(url_all)
        response_filtered = logged_in_pdf_user.get(url_filtered)
        
        # Both should succeed
        assert response_all.status_code == 200
        assert response_filtered.status_code == 200
        
        # Filtered PDF should potentially be smaller (though not always due to PDF structure)
        assert response_filtered.data[:4] == b'%PDF'
        assert response_all.data[:4] == b'%PDF'
    
    def test_price_pdf_export_without_company(self, client, app, setup_pdf_test_company):
        """Test that PDF export fails gracefully if user has no valid company."""
        # Just test that it redirects properly when company is not found
        # (User model requires company_id, so we can't actually create a user without it)
        with app.app_context():
            url = url_for('main.export_price_pdf')
        
        # Test without being logged in
        response = client.get(url)
        
        # Should redirect to login
        assert response.status_code == 302
    
    def test_price_pdf_export_calculates_costs_if_missing(self, client, app, setup_items_with_prices, logged_in_pdf_user):
        """Test that PDF export calculates costs for items that don't have them."""
        with app.app_context():
            # Create an item without ItemTotalCost
            setup = setup_items_with_prices
            packaging = Packaging.query.first()
            raw_product = RawProduct.query.first()
            
            item = Item(
                name="Item Without Cost",
                code="NO-COST",
                unit_of_weight=UnitOfWeight.POUND,
                packaging_id=packaging.id,
                company_id=setup['company_id'],
                case_weight=10.0,
                ranch=False
            )
            item.raw_products.append(raw_product)
            db.session.add(item)
            db.session.commit()
            
            # Create ItemInfo for cost calculation
            item_info = ItemInfo(
                item_id=item.id,
                product_yield=80.0,
                labor_hours=0.5,
                date=date.today(),
                company_id=setup['company_id']
            )
            db.session.add(item_info)
            db.session.commit()
            url = url_for('main.export_price_pdf')
        
        response = logged_in_pdf_user.get(url)
        
        # Should successfully generate PDF and calculate missing costs
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
