import pytest
from flask import url_for
from producepricer import db
from producepricer.models import Customer, CustomerEmail, Company

class TestCustomerErrors:
    
    def test_edit_nonexistent_customer(self, client, app, logged_in_user):
        """Test editing a customer that does not exist."""
        with app.app_context():
            url = url_for('main.edit_customer', customer_id=99999)
            
        response = client.post(url, data={'name': 'Test', 'email': 'test@test.com'}, follow_redirects=True)
        
        assert response.status_code == 404

    def test_delete_nonexistent_customer(self, client, app, logged_in_user):
        """Test deleting a customer that does not exist."""
        with app.app_context():
            url = url_for('main.delete_customer', customer_id=99999)
            
        response = client.post(url, follow_redirects=True)
        
        assert response.status_code == 404

    def test_add_email_to_nonexistent_customer(self, client, app, logged_in_user):
        """Test adding email to a customer that does not exist."""
        with app.app_context():
            url = url_for('main.add_customer_email', customer_id=99999)
            
        response = client.post(url, data={'email': 'test@test.com', 'label': 'Test'}, follow_redirects=True)
        
        assert response.status_code == 404

    def test_delete_nonexistent_email(self, client, app, logged_in_user):
        """Test deleting an email that does not exist."""
        with app.app_context():
            # Create a customer first
            customer = Customer(name="Test", email="test@test.com", company_id=logged_in_user.company_id)
            db.session.add(customer)
            db.session.commit()
            customer_id = customer.id
            
            url = url_for('main.delete_customer_email', customer_id=customer_id, email_id=99999)
            
        response = client.post(url, follow_redirects=True)
        
        assert response.status_code == 404

    def test_update_nonexistent_email(self, client, app, logged_in_user):
        """Test updating an email that does not exist."""
        with app.app_context():
            # Create a customer first
            customer = Customer(name="Test", email="test@test.com", company_id=logged_in_user.company_id)
            db.session.add(customer)
            db.session.commit()
            customer_id = customer.id
            
            url = url_for('main.update_customer_email', customer_id=customer_id, email_id=99999)
            
        response = client.post(url, data={'label': 'New'}, follow_redirects=True)
        
        assert response.status_code == 404
