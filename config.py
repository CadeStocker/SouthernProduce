# Copyright Cade Stocker 2026

"""
Configuration module for the ProducePricer application. This module defines the configuration classes for different environments
(development, production, testing) and loads environment variables using python-dotenv.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'devkey')
    WTF_CSRF_ENABLED = True
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
    
    # Notification thresholds
    NOTIFICATION_OUTLIER_PERCENT_THRESHOLD = float(
        os.environ.get('NOTIFICATION_OUTLIER_PERCENT_THRESHOLD', '10')
    )
    NOTIFICATION_PRICE_CHANGE_PERCENT_THRESHOLD = float(
        os.environ.get('NOTIFICATION_PRICE_CHANGE_PERCENT_THRESHOLD', '20')
    )
    
    # Email configuration
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    MAIL_USERNAME = os.environ.get('EMAIL_USER')
    MAIL_PASSWORD = os.environ.get('EMAIL_PASS')
    MAIL_DEFAULT_SENDER = os.environ.get('EMAIL_USER')
    RESET_PASS_TOKEN_MAX_AGE = 3600  # 1 hour
    
    # Database - check for production environment
    render_data_dir = '/var/data'
    if os.path.exists(render_data_dir):
        # Production on Render
        db_path = os.path.join(render_data_dir, 'site.db')
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'
        RECEIVING_IMAGES_DIR = os.path.join(render_data_dir, 'receiving_images')
    else:
        # Local development
        SQLALCHEMY_DATABASE_URI = None  # Will be set based on instance_path
        RECEIVING_IMAGES_DIR = None  # Will be set based on instance_path


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
