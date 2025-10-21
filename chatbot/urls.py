from django.urls import path
from .views import ChatbotAPIView, FileUploadView

app_name = 'chatbot'

urlpatterns = [
    path('chat/', ChatbotAPIView.as_view(), name='chat'),
    path('upload/', FileUploadView.as_view(), name='file_upload'),
]
