import json
from datetime import datetime, date, timedelta

import pytest

from producepricer import db
from producepricer.models import (
    BrandName,
    Company,
    CostHistory,
    GrowerOrDistributor,
    Notification,
    RawProduct,
    Seller,
    User
)


class TestNotifications:
    def test_poll_notifications_returns_unread_count(self, client, app, logged_in_user):
        with app.app_context():
            first = Notification(
                user_id=logged_in_user.id,
                company_id=logged_in_user.company_id,
                title='First',
                message='First message',
                category='info',
                created_at=datetime(2026, 4, 24, 9, 30)
            )
            second = Notification(
                user_id=logged_in_user.id,
                company_id=logged_in_user.company_id,
                title='Second',
                message='Second message',
                category='warning',
                created_at=datetime(2026, 4, 24, 10, 30)
            )
            db.session.add_all([first, second])
            db.session.commit()

        response = client.get('/notifications/poll?limit=5')
        assert response.status_code == 200
        data = response.get_json()

        assert data['unread_count'] == 2
        assert len(data['notifications']) == 2
        assert data['notifications'][0]['title'] == 'Second'
        assert data['notifications'][1]['title'] == 'First'

    def test_mark_notifications_read(self, client, app, logged_in_user):
        with app.app_context():
            notifications = [
                Notification(
                    user_id=logged_in_user.id,
                    company_id=logged_in_user.company_id,
                    title='Unread 1',
                    message='Message 1',
                    category='info'
                ),
                Notification(
                    user_id=logged_in_user.id,
                    company_id=logged_in_user.company_id,
                    title='Unread 2',
                    message='Message 2',
                    category='info'
                )
            ]
            db.session.add_all(notifications)
            db.session.commit()
            ids = [n.id for n in notifications]

        response = client.post(
            '/notifications/mark_read',
            data=json.dumps({'ids': ids}),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['updated'] == 2

        with app.app_context():
            unread_count = (
                Notification.query
                .filter_by(user_id=logged_in_user.id)
                .filter(Notification.read_at.is_(None))
                .count()
            )
            assert unread_count == 0

    def test_poll_notifications_respects_limit(self, client, app, logged_in_user):
        with app.app_context():
            notifications = [
                Notification(
                    user_id=logged_in_user.id,
                    company_id=logged_in_user.company_id,
                    title=f'Notif {index}',
                    message='Message',
                    category='info',
                    created_at=datetime(2026, 4, 24, 8, 0 + index)
                )
                for index in range(3)
            ]
            db.session.add_all(notifications)
            db.session.commit()

        response = client.get('/notifications/poll?limit=1')
        assert response.status_code == 200
        data = response.get_json()

        assert len(data['notifications']) == 1
        assert data['notifications'][0]['title'] == 'Notif 2'

    def test_mark_read_ignores_other_users(self, client, app, logged_in_user):
        with app.app_context():
            other_user = User(
                first_name='Other',
                last_name='User',
                email='other@test.com',
                password='password',
                company_id=logged_in_user.company_id
            )
            db.session.add(other_user)
            db.session.commit()

            other_notification = Notification(
                user_id=other_user.id,
                company_id=logged_in_user.company_id,
                title='Other user',
                message='Not for you',
                category='info'
            )
            db.session.add(other_notification)
            db.session.commit()

            other_id = other_notification.id

        response = client.post(
            '/notifications/mark_read',
            data=json.dumps({'ids': [other_id]}),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['updated'] == 0

    def test_receiving_log_creation_generates_notifications(self, client, app):
        with app.app_context():
            company = Company(name='Notif Co', admin_email='notif@test.com')
            db.session.add(company)
            db.session.commit()

            user = User(
                first_name='Notif',
                last_name='User',
                email='notif@test.com',
                password='password',
                company_id=company.id
            )
            db.session.add(user)

            raw_product = RawProduct(name='Test Oranges', company_id=company.id)
            brand = BrandName(name='Test Brand', company_id=company.id)
            seller = Seller(name='Test Seller', company_id=company.id)
            grower = GrowerOrDistributor(
                name='Test Grower',
                city='Test City',
                state='CA',
                company_id=company.id
            )
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()

            cost = CostHistory(
                cost=25.00,
                date=date.today() - timedelta(days=1),
                company_id=company.id,
                raw_product_id=raw_product.id
            )
            db.session.add(cost)
            db.session.commit()

            user_id = user.id
            company_id = company.id
            raw_id = raw_product.id
            brand_id = brand.id
            seller_id = seller.id
            grower_id = grower.id

        client.post('/login', data={
            'email': 'notif@test.com',
            'password': 'password'
        }, follow_redirects=True)

        payload = {
            'raw_product_id': raw_id,
            'pack_size_unit': 'lbs',
            'pack_size': 50.0,
            'brand_name_id': brand_id,
            'quantity_received': 100,
            'seller_id': seller_id,
            'temperature': 34.5,
            'hold_or_used': 'used',
            'grower_or_distributor_id': grower_id,
            'country_of_origin': 'USA',
            'received_by': 'Test Employee',
            'returned': 'No',
            'price_paid': 30.00
        }

        response = client.post(
            '/api/receiving_logs',
            data=json.dumps(payload),
            content_type='application/json'
        )

        assert response.status_code == 201

        with app.app_context():
            notifications = (
                Notification.query
                .filter_by(user_id=user_id, company_id=company_id)
                .order_by(Notification.created_at.desc())
                .all()
            )

            assert len(notifications) == 2
            categories = {n.category for n in notifications}
            assert 'info' in categories
            assert 'danger' in categories

    def test_receiving_log_below_threshold_no_outlier(self, client, app):
        with app.app_context():
            company = Company(name='Threshold Co', admin_email='threshold@test.com')
            db.session.add(company)
            db.session.commit()

            user = User(
                first_name='Threshold',
                last_name='User',
                email='threshold@test.com',
                password='password',
                company_id=company.id
            )
            db.session.add(user)

            raw_product = RawProduct(name='Test Apples', company_id=company.id)
            brand = BrandName(name='Test Brand', company_id=company.id)
            seller = Seller(name='Test Seller', company_id=company.id)
            grower = GrowerOrDistributor(
                name='Test Grower',
                city='Test City',
                state='CA',
                company_id=company.id
            )
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()

            cost = CostHistory(
                cost=25.00,
                date=date.today() - timedelta(days=1),
                company_id=company.id,
                raw_product_id=raw_product.id
            )
            db.session.add(cost)
            db.session.commit()

            user_id = user.id
            company_id = company.id
            raw_id = raw_product.id
            brand_id = brand.id
            seller_id = seller.id
            grower_id = grower.id

        client.post('/login', data={
            'email': 'threshold@test.com',
            'password': 'password'
        }, follow_redirects=True)

        payload = {
            'raw_product_id': raw_id,
            'pack_size_unit': 'lbs',
            'pack_size': 50.0,
            'brand_name_id': brand_id,
            'quantity_received': 100,
            'seller_id': seller_id,
            'temperature': 34.5,
            'hold_or_used': 'used',
            'grower_or_distributor_id': grower_id,
            'country_of_origin': 'USA',
            'received_by': 'Test Employee',
            'returned': 'No',
            'price_paid': 26.00
        }

        response = client.post(
            '/api/receiving_logs',
            data=json.dumps(payload),
            content_type='application/json'
        )

        assert response.status_code == 201

        with app.app_context():
            notifications = (
                Notification.query
                .filter_by(user_id=user_id, company_id=company_id)
                .all()
            )
            assert len(notifications) == 1
            assert notifications[0].category == 'info'

    def test_receiving_log_without_market_cost_no_outlier(self, client, app):
        with app.app_context():
            company = Company(name='No Market Co', admin_email='nomarket@test.com')
            db.session.add(company)
            db.session.commit()

            user = User(
                first_name='No',
                last_name='Market',
                email='nomarket@test.com',
                password='password',
                company_id=company.id
            )
            db.session.add(user)

            raw_product = RawProduct(name='Test Pears', company_id=company.id)
            brand = BrandName(name='Test Brand', company_id=company.id)
            seller = Seller(name='Test Seller', company_id=company.id)
            grower = GrowerOrDistributor(
                name='Test Grower',
                city='Test City',
                state='CA',
                company_id=company.id
            )
            db.session.add_all([raw_product, brand, seller, grower])
            db.session.commit()

            user_id = user.id
            company_id = company.id
            raw_id = raw_product.id
            brand_id = brand.id
            seller_id = seller.id
            grower_id = grower.id

        client.post('/login', data={
            'email': 'nomarket@test.com',
            'password': 'password'
        }, follow_redirects=True)

        payload = {
            'raw_product_id': raw_id,
            'pack_size_unit': 'lbs',
            'pack_size': 50.0,
            'brand_name_id': brand_id,
            'quantity_received': 100,
            'seller_id': seller_id,
            'temperature': 34.5,
            'hold_or_used': 'used',
            'grower_or_distributor_id': grower_id,
            'country_of_origin': 'USA',
            'received_by': 'Test Employee',
            'returned': 'No',
            'price_paid': 30.00
        }

        response = client.post(
            '/api/receiving_logs',
            data=json.dumps(payload),
            content_type='application/json'
        )

        assert response.status_code == 201

        with app.app_context():
            notifications = (
                Notification.query
                .filter_by(user_id=user_id, company_id=company_id)
                .all()
            )
            assert len(notifications) == 1
            assert notifications[0].category == 'info'
