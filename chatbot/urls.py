from django.urls import path
from .views import ChatbotAPIView, FileUploadView
from .admin_chat_views import (
    connect_to_user_chat, send_staff_message, get_active_sessions, 
    get_chat_history, end_chat_session, request_staff_assistance, get_user_chat_status,
    send_user_message
)

app_name = 'chatbot'

urlpatterns = [
    path('chat/', ChatbotAPIView.as_view(), name='chat'),
    path('upload/', FileUploadView.as_view(), name='file_upload'),
    
    # Admin chat endpoints
    path('admin/connect/', connect_to_user_chat, name='connect_to_user_chat'),
    path('admin/send_message/', send_staff_message, name='send_staff_message'),
    path('admin/active_sessions/', get_active_sessions, name='get_active_sessions'),
    path('admin/chat_history/<str:session_id>/', get_chat_history, name='get_chat_history'),
    path('admin/end_session/', end_chat_session, name='end_chat_session'),
    path('admin/request_assistance/', request_staff_assistance, name='request_staff_assistance'),
    path('admin/session_status/<str:session_id>/', get_user_chat_status, name='get_user_chat_status'),
    path('admin/send_user_message/', send_user_message, name='send_user_message'),
]
