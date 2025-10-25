from django.db import models
import os
from django.conf import settings
from django.contrib.auth.models import User


class ChatMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    session_id = models.CharField(max_length=100, help_text="Session ID for anonymous users")
    message = models.TextField(help_text="User's message")
    response = models.TextField(help_text="AI's response")
    timestamp = models.DateTimeField(auto_now_add=True)
    response_time = models.FloatField(null=True, blank=True, help_text="Response time in seconds")
    
    class Meta:
        ordering = ['-timestamp']
        
    def __str__(self):
        return f"Message from {self.user or self.session_id} at {self.timestamp}"


def user_document_path(instance, filename):
    """Generate file path for user documents: documents/session_id/filename"""
    return f'documents/{instance.chat_message.session_id}/{filename}'


class UploadedFile(models.Model):
    DOCUMENT = 'document'
    IMAGE = 'image'
    FILE_TYPES = [
        (DOCUMENT, 'Document'),
        (IMAGE, 'Image'),
    ]
    
    chat_message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='uploaded_files')
    file = models.FileField(upload_to=user_document_path)
    file_type = models.CharField(max_length=10, choices=FILE_TYPES)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    upload_time = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    processed_content = models.TextField(blank=True, help_text="Extracted text from the document/image")
    
    class Meta:
        ordering = ['-upload_time']
        
    def __str__(self):
        return f"{self.original_filename} uploaded to {self.chat_message.session_id}"
        
    def save(self, *args, **kwargs):
        # Auto-detect file type based on extension
        if not self.file_type:
            self.file_type = self._detect_file_type()
        
        if not self.file_size:
            self.file_size = self.file.size
        
        super().save(*args, **kwargs)
    
    def _detect_file_type(self):
        """Detect file type based on extension"""
        _, ext = os.path.splitext(self.file.name)
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        
        if ext.lower() in image_extensions:
            return self.IMAGE
        else:
            return self.DOCUMENT


class ActiveChatSession(models.Model):
    """
    Model to track active chat sessions between users and ZRA staff
    """
    STATUS_CHOICES = [
        ('pending', 'Pending - User waiting for staff'),
        ('active', 'Active - Staff connected'),
        ('closed', 'Closed - Session ended'),
    ]
    
    session_id = models.CharField(max_length=100, unique=True, help_text="Session ID from the original chat")
    user_id = models.CharField(max_length=100, help_text="User session ID or user identifier")
    staff_member = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                    help_text="ZRA staff member assigned to this chat")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    connected_at = models.DateTimeField(null=True, blank=True, help_text="When staff connected")
    closed_at = models.DateTimeField(null=True, blank=True, help_text="When session was closed")
    is_user_waiting_for_staff = models.BooleanField(default=False, help_text="Whether user requested staff help")
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"Chat session {self.session_id} - {self.status}"


class RealTimeChatMessage(models.Model):
    """
    Model to store real-time chat messages between users and ZRA staff
    """
    MESSAGE_TYPE_CHOICES = [
        ('user', 'User Message'),
        ('staff', 'Staff Message'),
        ('system', 'System Notification'),
    ]
    
    chat_session = models.ForeignKey(ActiveChatSession, on_delete=models.CASCADE, 
                                    related_name='real_time_messages')
    sender_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES)
    sender_id = models.CharField(max_length=100, help_text="ID of the sender (session ID for user, user ID for staff)")
    message = models.TextField(help_text="Message content")
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False, help_text="Whether message has been read by the recipient")
    
    class Meta:
        ordering = ['timestamp']
        
    def __str__(self):
        return f"{self.sender_type} message in {self.chat_session.session_id}"
