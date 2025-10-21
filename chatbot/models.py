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
