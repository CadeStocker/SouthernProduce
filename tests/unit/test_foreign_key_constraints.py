# Copyright Cade Stocker 2026
"""
Test foreign key constraints and deletion protections.

This test suite verifies that entities with references cannot be deleted,
and that appropriate error messages are shown to users. This prevents
database integrity violations.
"""

import pytest
from flask import url_for
from datetime import date
from app import db
from app.models import (
    Company, User, RawProduct, BrandName, Seller, GrowerOrDistributor,
    ReceivingLog, Item, Packaging, Customer, PriceSheet, PriceHistory,
    ItemInfo, ItemInventory, InventorySession, CostHistory
)


class TestBrandNameDeletion:
    """Test BrandName deletion protection when used in ReceivingLogs."""
    
    def test_cannot_delete_brand_with_receiving_logs(self, logged_in_user, client, app):
        """Brand names used in receiving logs cannot be deleted."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            # Create dependencies
            raw_product = RawProduct(name="Tomatoes", company_id=company_id)
            brand = BrandName(name="Fresh Farms", company_id=company_id)
            seller = Seller(name="Seller 1", company_id=company_id)
            grower = GrowerOrDistributor(
                name="Grower 1", company_id=company_id,
                city="City", state="State"
            )
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create receiving log that uses this brand
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit="lbs",
                pack_size=50.0,
                brand_name_id=brand.id,
                quantity_received=100,
                seller_id=seller.id,
                temperature=34.5,
                hold_or_used="used",
                grower_or_distributor_id=grower.id,
                country_of_origin="USA",
                received_by="Employee",
                company_id=company_id
            )
            db.session.add(log)
            db.session.commit()
            brand_id = brand.id
        
        # Attempt to delete brand
        response = client.post(
            url_for('main.delete_brand_name', brand_id=brand_id),
            follow_redirects=True
        )
        
        with app.app_context():
            # Verify deletion was prevented
            assert BrandName.query.get(brand_id) is not None
            assert b'Cannot delete' in response.data
            assert b'receiving log' in response.data
    
    def test_can_delete_unused_brand(self, logged_in_user, client, app):
        """Brand names not used in receiving logs can be deleted."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            # Create brand with no references
            brand = BrandName(name="Unused Brand", company_id=company_id)
            db.session.add(brand)
            db.session.commit()
            brand_id = brand.id
        
        # Delete brand
        response = client.post(
            url_for('main.delete_brand_name', brand_id=brand_id),
            follow_redirects=True
        )
        
        with app.app_context():
            # Verify deletion succeeded
            assert BrandName.query.get(brand_id) is None
            assert b'has been deleted' in response.data


class TestSellerDeletion:
    """Test Seller deletion protection when used in ReceivingLogs."""
    
    def test_cannot_delete_seller_with_receiving_logs(self, logged_in_user, client, app):
        """Sellers used in receiving logs cannot be deleted."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            # Create dependencies
            raw_product = RawProduct(name="Tomatoes", company_id=company_id)
            brand = BrandName(name="Brand", company_id=company_id)
            seller = Seller(name="Active Seller", company_id=company_id)
            grower = GrowerOrDistributor(
                name="Grower", company_id=company_id,
                city="City", state="State"
            )
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create receiving log that uses this seller
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit="lbs",
                pack_size=50.0,
                brand_name_id=brand.id,
                quantity_received=100,
                seller_id=seller.id,
                temperature=34.5,
                hold_or_used="used",
                grower_or_distributor_id=grower.id,
                country_of_origin="USA",
                received_by="Employee",
                company_id=company_id
            )
            db.session.add(log)
            db.session.commit()
            seller_id = seller.id
        
        # Attempt to delete seller
        response = client.post(
            url_for('main.delete_seller', seller_id=seller_id),
            follow_redirects=True
        )
        
        with app.app_context():
            # Verify deletion was prevented
            assert Seller.query.get(seller_id) is not None
            assert b'Cannot delete' in response.data
    
    def test_can_delete_unused_seller(self, logged_in_user, client, app):
        """Sellers not used in receiving logs can be deleted."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            seller = Seller(name="Unused Seller", company_id=company_id)
            db.session.add(seller)
            db.session.commit()
            seller_id = seller.id
        
        response = client.post(
            url_for('main.delete_seller', seller_id=seller_id),
            follow_redirects=True
        )
        
        with app.app_context():
            assert Seller.query.get(seller_id) is None
            assert b'has been deleted' in response.data


class TestGrowerDistributorDeletion:
    """Test GrowerOrDistributor deletion protection when used in ReceivingLogs."""
    
    def test_cannot_delete_grower_with_receiving_logs(self, logged_in_user, client, app):
        """Growers/Distributors used in receiving logs cannot be deleted."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            # Create dependencies
            raw_product = RawProduct(name="Tomatoes", company_id=company_id)
            brand = BrandName(name="Brand", company_id=company_id)
            seller = Seller(name="Seller", company_id=company_id)
            grower = GrowerOrDistributor(
                name="Active Grower", company_id=company_id,
                city="City", state="State"
            )
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create receiving log that uses this grower
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit="lbs",
                pack_size=50.0,
                brand_name_id=brand.id,
                quantity_received=100,
                seller_id=seller.id,
                temperature=34.5,
                hold_or_used="used",
                grower_or_distributor_id=grower.id,
                country_of_origin="USA",
                received_by="Employee",
                company_id=company_id
            )
            db.session.add(log)
            db.session.commit()
            grower_id = grower.id
        
        # Attempt to delete grower
        response = client.post(
            url_for('main.delete_grower_distributor', grower_id=grower_id),
            follow_redirects=True
        )
        
        with app.app_context():
            # Verify deletion was prevented
            assert GrowerOrDistributor.query.get(grower_id) is not None
            assert b'Cannot delete' in response.data
    
    def test_can_delete_unused_grower(self, logged_in_user, client, app):
        """Growers/Distributors not used in receiving logs can be deleted."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            grower = GrowerOrDistributor(
                name="Unused Grower", company_id=company_id,
                city="City", state="State"
            )
            db.session.add(grower)
            db.session.commit()
            grower_id = grower.id
        
        response = client.post(
            url_for('main.delete_grower_distributor', grower_id=grower_id),
            follow_redirects=True
        )
        
        with app.app_context():
            assert GrowerOrDistributor.query.get(grower_id) is None
            assert b'has been deleted' in response.data


class TestRawProductDeletion:
    """Test RawProduct deletion protection when used in ReceivingLogs."""
    
    def test_cannot_delete_raw_product_with_receiving_logs(self, logged_in_user, client, app):
        """Raw products used in receiving logs cannot be deleted."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            # Create dependencies
            raw_product = RawProduct(name="Tomatoes", company_id=company_id)
            brand = BrandName(name="Brand", company_id=company_id)
            seller = Seller(name="Seller", company_id=company_id)
            grower = GrowerOrDistributor(
                name="Grower", company_id=company_id,
                city="City", state="State"
            )
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create receiving log that uses this raw product
            log = ReceivingLog(
                raw_product_id=raw_product.id,
                pack_size_unit="lbs",
                pack_size=50.0,
                brand_name_id=brand.id,
                quantity_received=100,
                seller_id=seller.id,
                temperature=34.5,
                hold_or_used="used",
                grower_or_distributor_id=grower.id,
                country_of_origin="USA",
                received_by="Employee",
                company_id=company_id
            )
            db.session.add(log)
            db.session.commit()
            raw_product_id = raw_product.id
        
        # Attempt to delete raw product
        response = client.post(
            url_for('main.delete_raw_product', raw_product_id=raw_product_id),
            follow_redirects=True
        )
        
        with app.app_context():
            # Verify deletion was prevented
            assert RawProduct.query.get(raw_product_id) is not None
            assert b'Cannot delete' in response.data
            assert b'receiving log' in response.data


class TestPackagingDeletion:
    """Test Packaging deletion protection when used in Items."""
    
    def test_cannot_delete_packaging_used_by_items(self, logged_in_user, client, app):
        """Packaging types used by items cannot be deleted."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            # Create packaging and item
            packaging = Packaging(packaging_type="Box 5lb", company_id=company_id)
            db.session.add(packaging)
            db.session.commit()
            
            item = Item(
                name="Tomatoes Box",
                code="TBOX5",
                unit_of_weight="POUND",
                packaging_id=packaging.id,
                company_id=company_id
            )
            db.session.add(item)
            db.session.commit()
            packaging_id = packaging.id
        
        # Attempt to delete packaging
        response = client.post(
            url_for('main.delete_packaging', packaging_id=packaging_id),
            follow_redirects=True
        )
        
        with app.app_context():
            # Verify deletion was prevented
            result = Packaging.query.get(packaging_id)
            assert result is not None
            assert b'Cannot delete' in response.data
            assert b'item' in response.data
    
    def test_can_delete_unused_packaging(self, logged_in_user, client, app):
        """Unused packaging can be deleted."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            packaging = Packaging(packaging_type="Unused Box", company_id=company_id)
            db.session.add(packaging)
            db.session.commit()
            packaging_id = packaging.id
        
        response = client.post(
            url_for('main.delete_packaging', packaging_id=packaging_id),
            follow_redirects=True
        )
        
        with app.app_context():
            assert Packaging.query.get(packaging_id) is None


class TestCustomerDeletion:
    """Test Customer deletion protection when used in PriceSheets/PriceHistory."""
    
    def test_cannot_delete_customer_with_price_sheets(self, logged_in_user, client, app):
        """Customers with price sheets cannot be deleted."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            # Create customer and price sheet
            customer = Customer(
                name="Active Customer",
                email="customer@example.com",
                company_id=company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            price_sheet = PriceSheet(
                name="Price Sheet 1",
                date=date(2026, 5, 15),
                company_id=company_id,
                customer_id=customer.id
            )
            db.session.add(price_sheet)
            db.session.commit()
            customer_id = customer.id
        
        # Attempt to delete customer
        response = client.post(
            url_for('main.delete_customer', customer_id=customer_id),
            follow_redirects=True
        )
        
        with app.app_context():
            # Verify deletion was prevented
            customer_exists = Customer.query.get(customer_id)
            assert customer_exists is not None
            assert b'Cannot delete' in response.data
            assert b'price sheet' in response.data
    
    def test_cannot_delete_customer_with_price_history(self, logged_in_user, client, app):
        """Customers with price history cannot be deleted."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            # Create raw product and customer
            raw_product = RawProduct(name="Tomatoes", company_id=company_id)
            db.session.add(raw_product)
            db.session.commit()
            
            customer = Customer(
                name="Customer with History",
                email="history@example.com",
                company_id=company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            # Add price history for this customer
            price_history = PriceHistory(
                item_id=raw_product.id,
                date=date(2026, 5, 15),
                company_id=company_id,
                customer_id=customer.id,
                price=10.0
            )
            db.session.add(price_history)
            db.session.commit()
            customer_id = customer.id
        
        # Attempt to delete customer
        response = client.post(
            url_for('main.delete_customer', customer_id=customer_id),
            follow_redirects=True
        )
        
        with app.app_context():
            # Verify deletion was prevented
            customer_exists = Customer.query.get(customer_id)
            assert customer_exists is not None
            assert b'Cannot delete' in response.data
            assert b'price history' in response.data


class TestItemDeletion:
    """Test Item deletion with related records."""
    
    def test_cannot_delete_item_with_price_sheets(self, logged_in_user, client, app):
        """Items on price sheets cannot be deleted."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            # Create item, customer, and price sheet
            packaging = Packaging(packaging_type="Box", company_id=company_id)
            db.session.add(packaging)
            db.session.commit()
            
            item = Item(
                name="Test Item",
                code="TEST",
                unit_of_weight="POUND",
                packaging_id=packaging.id,
                company_id=company_id
            )
            db.session.add(item)
            db.session.commit()
            
            customer = Customer(
                name="Test Customer",
                email="test@example.com",
                company_id=company_id
            )
            db.session.add(customer)
            db.session.commit()
            
            price_sheet = PriceSheet(
                name="Price Sheet",
                date=date(2026, 5, 15),
                company_id=company_id,
                customer_id=customer.id
            )
            db.session.add(price_sheet)
            price_sheet.items.append(item)
            db.session.commit()
            item_id = item.id
        
        # Attempt to delete item
        response = client.post(
            url_for('main.delete_item', item_id=item_id),
            follow_redirects=True
        )
        
        with app.app_context():
            # Verify deletion was prevented
            assert Item.query.get(item_id) is not None
            assert b'Cannot delete' in response.data
            assert b'price sheet' in response.data
    
    def test_can_delete_item_with_cost_history(self, logged_in_user, client, app):
        """Items with cost history should be deletable (cleanup of dependent records)."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            # Create item and related data
            packaging = Packaging(packaging_type="Box", company_id=company_id)
            db.session.add(packaging)
            db.session.commit()
            
            item = Item(
                name="Test Item",
                code="TEST",
                unit_of_weight="POUND",
                packaging_id=packaging.id,
                company_id=company_id
            )
            db.session.add(item)
            db.session.commit()
            
            item_info = ItemInfo(
                product_yield=0.9,
                item_id=item.id,
                labor_hours=2.0,
                date=date(2026, 5, 15),
                company_id=company_id
            )
            db.session.add(item_info)
            db.session.commit()
            item_id = item.id
        
        # Delete item
        response = client.post(
            url_for('main.delete_item', item_id=item_id),
            follow_redirects=True
        )
        
        with app.app_context():
            # Should delete successfully, cleaning up dependent records
            assert Item.query.get(item_id) is None
            assert ItemInfo.query.filter_by(item_id=item_id).count() == 0


class TestMultipleReferences:
    """Test scenarios with multiple foreign key references."""
    
    def test_brand_with_multiple_receiving_logs(self, logged_in_user, client, app):
        """Cannot delete brand used in multiple receiving logs."""
        with app.app_context():
            company_id = logged_in_user.company_id
            
            # Setup
            raw_product = RawProduct(name="Tomatoes", company_id=company_id)
            brand = BrandName(name="Brand", company_id=company_id)
            seller = Seller(name="Seller", company_id=company_id)
            grower = GrowerOrDistributor(
                name="Grower", company_id=company_id,
                city="City", state="State"
            )
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()
            
            # Create multiple receiving logs
            for i in range(3):
                log = ReceivingLog(
                    raw_product_id=raw_product.id,
                    pack_size_unit="lbs",
                    pack_size=50.0,
                    brand_name_id=brand.id,
                    quantity_received=100 + i,
                    seller_id=seller.id,
                    temperature=34.5,
                    hold_or_used="used",
                    grower_or_distributor_id=grower.id,
                    country_of_origin="USA",
                    received_by="Employee",
                    company_id=company_id
                )
                db.session.add(log)
            db.session.commit()
            brand_id = brand.id
        
        # Attempt to delete
        response = client.post(
            url_for('main.delete_brand_name', brand_id=brand_id),
            follow_redirects=True
        )
        
        with app.app_context():
            # Verify deletion prevented and error mentions count
            assert BrandName.query.get(brand_id) is not None
            assert b'3 receiving log' in response.data or b'used by' in response.data
