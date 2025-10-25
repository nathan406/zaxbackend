"""
URL configuration for zax_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.conf import settings
from django.conf.urls.static import static
import os

def api_root(request):
    return JsonResponse({
        'message': 'ZAX - Zambia Revenue Authority Chatbot API',
        'version': '1.0',
        'status': 'running',
        'debug': settings.DEBUG,
        'allowed_hosts': settings.ALLOWED_HOSTS,
        'cors_origins': getattr(settings, 'CORS_ALLOWED_ORIGINS', []),
        'environment': {
            'DATABASE_URL': 'configured' if os.getenv('DATABASE_URL') else 'not configured',
            'DEBUG': os.getenv('DEBUG', 'not set'),
            'CORS_ALLOWED_ORIGINS': os.getenv('CORS_ALLOWED_ORIGINS', 'not set'),
        },
        'endpoints': {
            'chat': '/api/chatbot/chat/',
            'debug': '/api/debug/',
            'admin': '/admin/',
        }
    })

def debug_info(request):
    """Debug endpoint to check deployment configuration"""
    return JsonResponse({
        'django_settings': {
            'DEBUG': settings.DEBUG,
            'ALLOWED_HOSTS': settings.ALLOWED_HOSTS,
            'CORS_ALLOWED_ORIGINS': getattr(settings, 'CORS_ALLOWED_ORIGINS', []),
            'CORS_ALLOW_CREDENTIALS': getattr(settings, 'CORS_ALLOW_CREDENTIALS', False),
        },
        'environment_variables': {
            'DEBUG': os.getenv('DEBUG'),
            'CORS_ALLOWED_ORIGINS': os.getenv('CORS_ALLOWED_ORIGINS'),
            'ALLOWED_HOSTS': os.getenv('ALLOWED_HOSTS'),
            'DATABASE_URL': 'set' if os.getenv('DATABASE_URL') else 'not set',
            'SECRET_KEY': 'set' if os.getenv('SECRET_KEY') else 'not set',
            'OPENAI_API_KEY': 'set' if os.getenv('OPENAI_API_KEY') else 'not set',
        },
        'request_info': {
            'method': request.method,
            'path': request.path,
            'headers': dict(request.headers),
            'origin': request.headers.get('Origin', 'not set'),
        }
    })

def health_check(request):
    """Simple health check that doesn't require database"""
    return JsonResponse({
        'status': 'healthy',
        'message': 'ZAX Backend is running',
        'timestamp': '2025-08-06T07:45:00Z',
        'database_required': False
    })

urlpatterns = [
    path('', api_root, name='root'),  # Add root endpoint
    path('admin/', admin.site.urls),
    path('api/', api_root, name='api_root'),
    path('api/debug/', debug_info, name='debug_info'),  # Debug endpoint
    path('api/health/', health_check, name='health_check'),  # Health check
    path('api/chatbot/', include('chatbot.urls')),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
