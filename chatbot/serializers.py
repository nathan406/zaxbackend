from rest_framework import serializers
from .models import UploadedFile, ChatMessage


class UploadedFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedFile
        fields = ['id', 'file', 'file_type', 'original_filename', 'file_size', 'upload_time', 'processed', 'processed_content']
        read_only_fields = ['file_type', 'file_size', 'upload_time', 'processed', 'processed_content']


class ChatMessageWithFilesSerializer(serializers.ModelSerializer):
    uploaded_files = UploadedFileSerializer(many=True, read_only=True)
    
    class Meta:
        model = ChatMessage
        fields = ['id', 'user', 'session_id', 'message', 'response', 'timestamp', 'response_time', 'uploaded_files']