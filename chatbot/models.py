from django.db import models
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
