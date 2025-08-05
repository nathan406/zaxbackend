from django.urls import path
from .views import ChatbotAPIView

app_name = 'chatbot'

urlpatterns = [
    path('chat/', ChatbotAPIView.as_view(), name='chat'),
]
