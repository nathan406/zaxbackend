#!/usr/bin/env python3
"""
Generate a secure Django SECRET_KEY for production deployment
"""
import secrets
import string

def generate_secret_key(length=50):
    """Generate a secure random secret key"""
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*(-_=+)'
    return ''.join(secrets.choice(alphabet) for _ in range(length))

if __name__ == "__main__":
    secret_key = generate_secret_key()
    print("=" * 60)
    print("🔐 SECURE SECRET KEY FOR PRODUCTION")
    print("=" * 60)
    print(f"SECRET_KEY={secret_key}")
    print("=" * 60)
    print("⚠️  IMPORTANT: Keep this secret and never commit it to version control!")
    print("📋 Copy this value to your Render environment variables")
    print("=" * 60)