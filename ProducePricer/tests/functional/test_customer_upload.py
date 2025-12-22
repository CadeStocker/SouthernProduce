import pytest
import io
import os
from flask import url_for
from producepricer import db
from producepricer.models import Customer

class TestCustomerUpload:
    
    def test_upload_customer_csv_success(self, client, app, logged_in_user, tmp_path):
        """Test successfully uploading a customer CSV."""
        # Configure upload folder
        app.config['UPLOAD_FOLDER'] = str(tmp_path)
        
        csv_content = "name,email\nNew Customer 1,new1@test.com\nNew Customer 2,new2@test.com"
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'customers.csv')
        }
        
        with app.app_context():
            url = url_for('main.upload_customer_csv')
            
        response = client.post(url, data=data, content_type='multipart/form-data', follow_redirects=True)
        
        assert response.status_code == 200
        
        with app.app_context():
            c1 = Customer.query.filter_by(email='new1@test.com').first()
            c2 = Customer.query.filter_by(email='new2@test.com').first()
            assert c1 is not None
            assert c1.name == 'New Customer 1'
            assert c2 is not None
            assert c2.name == 'New Customer 2'

    def test_upload_customer_csv_missing_columns(self, client, app, logged_in_user, tmp_path):
        """Test uploading CSV with missing columns."""
        app.config['UPLOAD_FOLDER'] = str(tmp_path)
        
        csv_content = "name\nNew Customer 1"
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'customers.csv')
        }
        
        with app.app_context():
            url = url_for('main.upload_customer_csv')
            
        response = client.post(url, data=data, content_type='multipart/form-data', follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Missing columns' in response.data

    def test_upload_customer_csv_no_file(self, client, app, logged_in_user):
        """Test uploading without a file."""
        with app.app_context():
            url = url_for('main.upload_customer_csv')
            
        response = client.post(url, data={}, follow_redirects=True)
        
        assert response.status_code == 200
        # The form validation should fail with "This field is required"
        assert b'This field is required' in response.data

    def test_upload_customer_csv_empty_filename(self, client, app, logged_in_user):
        """Test uploading with empty filename."""
        with app.app_context():
            url = url_for('main.upload_customer_csv')
            
        data = {
            'file': (io.BytesIO(b""), '')
        }
        
        response = client.post(url, data=data, content_type='multipart/form-data', follow_redirects=True)
        
        assert response.status_code == 200
        # The form validation should fail with "This field is required" or similar
        assert b'This field is required' in response.data or b'No selected file' in response.data
