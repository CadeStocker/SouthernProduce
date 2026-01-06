"""QR Code generation utilities for API keys."""
import qrcode
import io
import base64
import json
from flask import url_for


def generate_api_key_qr_code(api_key, device_name, api_base_url=None):
    """Generate a QR code for an API key.
    
    The QR code encodes a JSON object with the API configuration:
    {
        "type": "api_key",
        "key": "the-api-key",
        "device_name": "iPad Pro 1",
        "api_url": "https://your-domain.com"
    }
    
    Args:
        api_key: The API key string
        device_name: The name of the device
        api_base_url: Base URL of the API (e.g., "https://your-domain.com")
        
    Returns:
        Base64 encoded PNG image data that can be embedded in HTML
    """
    # Create the configuration object
    config = {
        "type": "api_key",
        "key": api_key,
        "device_name": device_name,
        "api_url": api_base_url or "http://localhost:5000"
    }
    
    # Convert to JSON string
    qr_data = json.dumps(config)
    
    # Create QR code
    qr = qrcode.QRCode(
        version=None,  # Auto-determine size
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    # Create the image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64 for embedding in HTML
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    img_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
    
    return f"data:image/png;base64,{img_base64}"


def generate_simple_qr_code(data):
    """Generate a simple QR code from any string data.
    
    Args:
        data: String data to encode in the QR code
        
    Returns:
        Base64 encoded PNG image data
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    img_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
    
    return f"data:image/png;base64,{img_base64}"


def generate_qr_code_bytes(data):
    """Generate a QR code and return raw PNG bytes.
    
    Useful for downloading QR codes as files.
    
    Args:
        data: String data to encode in the QR code
        
    Returns:
        BytesIO object containing PNG data
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return img_io
