from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import parser_classes
from rest_framework.parsers import JSONParser
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from .models import ActiveChatSession, RealTimeChatMessage
import json
import logging

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([JSONParser])
def connect_to_user_chat(request):
    """
    Endpoint for ZRA staff to connect to a user's chat session
    """
    try:
        session_id = request.data.get('session_id')
        if not session_id:
            return Response({'error': 'Session ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the active chat session
        active_session = get_object_or_404(ActiveChatSession, session_id=session_id)
        
        # Check if the session is already connected to another staff member
        if active_session.status == 'active' and active_session.staff_member:
            staff_member_name = getattr(active_session.staff_member, 'username', 'Unknown Staff')
            return Response({
                'error': 'Session is already connected to another staff member',
                'connected_to': staff_member_name
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update the session to active status with current staff member
        # For development purposes, we'll use a default staff name if no auth
        staff_user = request.user if request.user.is_authenticated else None
        active_session.staff_member = staff_user
        active_session.status = 'active'
        active_session.connected_at = timezone.now()
        active_session.is_user_waiting_for_staff = False  # User no longer waiting
        active_session.save()
        
        # Send system message that staff has joined
        staff_name = staff_user.username if staff_user else "Staff Member"
        RealTimeChatMessage.objects.create(
            chat_session=active_session,
            sender_type='system',
            sender_id=str(staff_user.id) if staff_user else "system",
            message=f"ZRA staff member {staff_name} has joined the chat"
        )
        
        return Response({
            'message': 'Successfully connected to user chat',
            'session_id': active_session.session_id,
            'status': active_session.status,
            'connected_at': active_session.connected_at.isoformat()
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error connecting to user chat: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([JSONParser])
def send_staff_message(request):
    """
    Endpoint for ZRA staff to send a message to a user
    """
    try:
        session_id = request.data.get('session_id')
        message_content = request.data.get('message')
        
        if not session_id or not message_content:
            return Response({'error': 'Session ID and message are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the active chat session
        active_session = get_object_or_404(ActiveChatSession, session_id=session_id)
        
        # Check if this staff member is assigned to this session
        # For development, we'll skip this check if the user isn't authenticated
        if active_session.staff_member and active_session.staff_member != request.user:
            if request.user.is_authenticated:
                return Response({'error': 'You are not assigned to this chat session'}, status=status.HTTP_403_FORBIDDEN)
            # If not authenticated, allow it for development purposes
        
        # Create the message
        staff_user = request.user if request.user.is_authenticated else None
        staff_message = RealTimeChatMessage.objects.create(
            chat_session=active_session,
            sender_type='staff',
            sender_id=str(staff_user.id) if staff_user else "staff_system",
            message=message_content
        )
        
        return Response({
            'message_id': staff_message.id,
            'message': staff_message.message,
            'sender_type': staff_message.sender_type,
            'timestamp': staff_message.timestamp.isoformat()
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error sending staff message: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_active_sessions(request):
    """
    Get all active chat sessions that need staff attention
    """
    try:
        # Get all active sessions (pending or active)
        active_sessions = ActiveChatSession.objects.filter(
            status__in=['pending', 'active']
        ).order_by('-created_at')
        
        sessions_data = []
        for session in active_sessions:
            latest_message = session.real_time_messages.order_by('-timestamp').first()
            latest_message_content = latest_message.message if latest_message else None
            latest_message_time = latest_message.timestamp.isoformat() if latest_message else None
            
            session_data = {
                'session_id': session.session_id,
                'status': session.status,
                'user_id': session.user_id,
                'created_at': session.created_at.isoformat(),
                'connected_at': session.connected_at.isoformat() if session.connected_at else None,
                'staff_member': session.staff_member.username if session.staff_member else None,
                'is_user_waiting_for_staff': session.is_user_waiting_for_staff,
                'latest_message': latest_message_content,
                'latest_message_time': latest_message_time
            }
            sessions_data.append(session_data)
        
        return Response({
            'active_sessions': sessions_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error getting active sessions: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_chat_history(request, session_id):
    """
    Get chat history for a specific session
    """
    try:
        active_session = get_object_or_404(ActiveChatSession, session_id=session_id)
        
        # Check if this staff member is assigned to this session (for active sessions)
        # For development, we'll skip this check if the user isn't authenticated
        if (active_session.status == 'active' and 
            active_session.staff_member is not None and 
            active_session.staff_member != request.user):
            if request.user.is_authenticated:
                return Response({'error': 'You are not assigned to this chat session'}, status=status.HTTP_403_FORBIDDEN)
            # If not authenticated, allow it for development purposes
        
        # Get all messages for this session
        messages = active_session.real_time_messages.all().order_by('timestamp')
        
        messages_data = []
        for message in messages:
            message_data = {
                'id': message.id,
                'sender_type': message.sender_type,
                'sender_id': message.sender_id,
                'message': message.message,
                'timestamp': message.timestamp.isoformat(),
                'is_read': message.is_read
            }
            messages_data.append(message_data)
        
        # Also get any files associated with this session through regular ChatMessage
        from .models import ChatMessage, UploadedFile
        # Get regular chat messages for this session that might have files
        session_chat_messages = ChatMessage.objects.filter(session_id=session_id).prefetch_related('uploaded_files')
        
        files_data = []
        for chat_msg in session_chat_messages:
            uploaded_files = chat_msg.uploaded_files.all()
            for uploaded_file in uploaded_files:
                # Safely build the full media URL to prevent server crashes
                try:
                    base_url = request.build_absolute_uri('/')[:-1] if request.build_absolute_uri('/')[:-1] else settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'http://localhost:8000'
                    full_media_url = f"{base_url}{settings.MEDIA_URL}{uploaded_file.file.name}"
                except:
                    # Fallback to a default URL format if there are issues
                    full_media_url = f"{settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'http://localhost:8000'}{settings.MEDIA_URL}{uploaded_file.file.name}"
                
                # Provide file URL for staff access (relative to media root)
                files_data.append({
                    'id': uploaded_file.id,
                    'original_filename': uploaded_file.original_filename,
                    'file_type': uploaded_file.file_type,
                    'file_size': uploaded_file.file_size,
                    'upload_time': uploaded_file.upload_time.isoformat(),
                    'processed_content': uploaded_file.processed_content if uploaded_file.processed_content else '',
                    'processed': uploaded_file.processed,
                    'file_path': uploaded_file.file.name,  # File path relative to media root
                    'full_media_url': full_media_url,  # Complete URL to access the file
                    'associated_with_message': chat_msg.message[:50] + "..." if len(chat_msg.message) > 50 else chat_msg.message
                })
        
        return Response({
            'session_id': session_id,
            'messages': messages_data,
            'files': files_data  # Include files associated with the session
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([JSONParser])
def end_chat_session(request):
    """
    End a chat session
    """
    try:
        session_id = request.data.get('session_id')
        if not session_id:
            return Response({'error': 'Session ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        active_session = get_object_or_404(ActiveChatSession, session_id=session_id)
        
        # Check if this staff member is assigned to this session
        # For development, we'll skip this check if the user isn't authenticated
        if active_session.staff_member and active_session.staff_member != request.user:
            if request.user.is_authenticated:
                return Response({'error': 'You are not assigned to this chat session'}, status=status.HTTP_403_FORBIDDEN)
            # If not authenticated, allow it for development purposes
        
        # Update the session status to closed
        active_session.status = 'closed'
        active_session.closed_at = timezone.now()
        active_session.save()
        
        # Send system message that chat has ended
        staff_user = request.user if request.user.is_authenticated else None
        staff_name = staff_user.username if staff_user else "Staff Member"
        RealTimeChatMessage.objects.create(
            chat_session=active_session,
            sender_type='system',
            sender_id=str(staff_user.id) if staff_user else "system",
            message=f"ZRA staff member {staff_name} has ended the chat"
        )
        
        return Response({
            'message': 'Chat session ended successfully',
            'session_id': active_session.session_id,
            'status': active_session.status
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error ending chat session: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def send_user_message(request):
    """
    Endpoint for users to send a message to staff during their chat
    """
    try:
        session_id = request.data.get('session_id')
        message_content = request.data.get('message')
        
        if not session_id or not message_content:
            return Response({'error': 'Session ID and message are required'}, status=status.HTTP_400_BAD_REQUEST)

        # Get the active chat session
        active_session = get_object_or_404(ActiveChatSession, session_id=session_id)
        
        # Create the user message in the real-time chat
        user_message = RealTimeChatMessage.objects.create(
            chat_session=active_session,
            sender_type='user',  # This is the key - user messages have sender_type='user'
            sender_id=active_session.user_id,  # Use the user ID from the session
            message=message_content
        )
        
        return Response({
            'message_id': user_message.id,
            'message': user_message.message,
            'sender_type': user_message.sender_type,
            'timestamp': user_message.timestamp.isoformat()
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error sending user message: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def request_staff_assistance(request):
    """
    Endpoint for users to request staff assistance during their chat
    """
    try:
        session_id = request.data.get('session_id')
        user_id = request.data.get('user_id', 'anonymous')
        
        if not session_id:
            return Response({'error': 'Session ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create or update the active chat session
        active_session, created = ActiveChatSession.objects.get_or_create(
            session_id=session_id,
            defaults={
                'user_id': user_id,
                'is_user_waiting_for_staff': True
            }
        )
        
        if not created:
            # If session already exists, just update the status and waiting flag
            active_session.status = 'pending'
            active_session.is_user_waiting_for_staff = True
            active_session.save()
        
        # Send system message that user is requesting staff help
        RealTimeChatMessage.objects.create(
            chat_session=active_session,
            sender_type='system',
            sender_id=user_id,
            message="User has requested assistance from ZRA staff"
        )
        
        return Response({
            'message': 'Staff assistance requested successfully',
            'session_id': active_session.session_id,
            'status': active_session.status
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error requesting staff assistance: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_user_chat_status(request, session_id):
    """
    Get the status of a user's chat session (for frontend to know if staff is connected)
    """
    try:
        active_session = ActiveChatSession.objects.filter(session_id=session_id).first()
        
        if not active_session:
            return Response({
                'session_id': session_id,
                'status': 'not_found',
                'is_connected_to_staff': False
            }, status=status.HTTP_200_OK)
        
        # Safely access staff member information
        staff_member_name = None
        if hasattr(active_session, 'staff_member') and active_session.staff_member:
            try:
                staff_member_name = active_session.staff_member.username
            except AttributeError:
                staff_member_name = None
        
        return Response({
            'session_id': session_id,
            'status': active_session.status,
            'is_connected_to_staff': active_session.status == 'active',
            'staff_member': staff_member_name,
            'is_user_waiting_for_staff': active_session.is_user_waiting_for_staff
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error getting user chat status: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)