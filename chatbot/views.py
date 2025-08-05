from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from .models import ChatMessage
from openai import OpenAI
import time
import logging
import requests
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)

class ChatbotAPIView(APIView):
    def __init__(self):
        super().__init__()
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=3.0  # 3 second timeout
        )
    
    def log_to_terminal(self, session_id, user_message, success, ai_response=None, error=None, response_time=None):
        """Log chat interaction to terminal with clear formatting"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        status_symbol = "✅" if success else "❌"
        
        print(f"\n{'='*80}")
        print(f"[{timestamp}] CHAT INTERACTION {status_symbol}")
        print(f"Session: {session_id}")
        print(f"Status: {'SUCCESS' if success else 'ERROR'}")
        print(f"{'='*80}")
        
        print(f"👤 USER MESSAGE:")
        print(f"   {user_message}")
        
        if ai_response:
            print(f"\n🤖 AI RESPONSE:")
            print(f"   {ai_response[:200]}{'...' if len(ai_response) > 200 else ''}")
        
        if error:
            print(f"\n❌ ERROR:")
            print(f"   {error}")
        
        if response_time:
            print(f"\n⏱️  RESPONSE TIME: {response_time:.2f}s")
        
        print(f"{'='*80}\n")
        
    def is_greeting(self, message):
        """Check if the message is a simple greeting (not a specific help request)"""
        message_lower = message.lower().strip()
        
        # Simple greetings only - no specific requests
        simple_greetings = [
            r'^(hi|hello|hey|greetings)$',
            r'^(hi|hello|hey|greetings)\s*[.!]*$',
            r'^good\s+(morning|afternoon|evening)$',
            r'^(how are you|what\'s up|whats up|sup)$',
            r'^(what can you do|what do you do|who are you)$',
            r'^(help|assist|support)$',
            r'^can you help$',
            r'^(start|begin|getting started)$'
        ]
        
        # Only return True for simple greetings, not specific requests
        for pattern in simple_greetings:
            if re.search(pattern, message_lower):
                return True
        
        # If message contains specific ZRA/tax terms, it's not just a greeting
        if self.is_zra_related(message):
            return False
            
        return False
        
    def is_zra_related(self, message):
        """Check if the message is related to ZRA/tax matters"""
        zra_keywords = [
            'tax', 'zra', 'zambia revenue authority', 'vat', 'paye', 'income tax',
            'corporate tax', 'customs', 'excise', 'duty', 'filing', 'return',
            'registration', 'tpin', 'withholding', 'penalty', 'compliance',
            'revenue', 'taxation', 'levy', 'assessment', 'audit', 'refund',
            'business', 'company', 'individual', 'taxpayer', 'declaration',
            'payment', 'deadline', 'form', 'certificate', 'license'
        ]
        
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in zra_keywords)
    
    def get_greeting_response(self):
        """Generate a friendly greeting response for ZRA context"""
        return """Hello! 👋 I'm ZAX, your friendly AI assistant for the Zambia Revenue Authority (ZRA).

I'm here to help you with all your ZRA and tax-related questions, including:

📋 **Tax Services:**
• Tax registration and TPIN applications
• Income Tax, VAT, PAYE, and Corporate Tax
• Tax filing procedures and deadlines
• Tax compliance and penalty information

🏢 **Business Services:**
• Business registration tax requirements
• Customs and Excise duties
• Withholding tax procedures
• Tax certificates and clearances

💡 **General Support:**
• ZRA office locations and contacts
• Required documents and forms
• Payment methods and procedures
• Appeals and dispute resolution

How can I assist you with your tax matters today? Feel free to ask me anything related to ZRA services! 😊"""
    
    def get_flexible_context_prompt(self, user_message, is_greeting=False):
        """Create a more flexible context for the chatbot"""
        if is_greeting:
            return f"User is greeting you. Respond with the friendly ZRA introduction message. User said: {user_message}"
        
        base_context = """You are ZAX, a helpful and knowledgeable AI assistant for the Zambia Revenue Authority (ZRA). 
You are friendly, professional, and always ready to help with ZRA and Zambian tax-related matters.

Your expertise includes:
- All types of taxes (Income, VAT, PAYE, Corporate, Withholding)
- Tax registration and TPIN applications
- Business registration tax requirements
- Customs and Excise duties
- Tax filing procedures and deadlines
- Tax compliance and penalties
- ZRA services and office information
- Payment procedures and methods
- Appeals and dispute resolution

Guidelines for responses:
1. Be warm, helpful, and professional
2. Provide clear, step-by-step guidance when needed
3. Include relevant deadlines, requirements, and contact information
4. If you're unsure about specific details, recommend contacting ZRA directly
5. Use emojis occasionally to make responses friendly
6. For complex queries, break down information into easy-to-understand sections

FLEXIBILITY RULES:
- If someone asks about general business matters that relate to taxes, help them
- If someone asks about government services that connect to ZRA, provide guidance
- If someone needs help understanding tax implications of life events (marriage, death, etc.), assist them
- Only redirect to ZRA-only topics if the question is completely unrelated (like sports, entertainment, etc.)

For completely unrelated topics, politely say: "I specialize in ZRA and tax-related matters. While I'd love to chat about other topics, I'm here to help you with tax questions, filing procedures, and ZRA services. Is there anything tax-related I can assist you with?"
"""
        
        base_context += f"\nUser Question: {user_message}\n\nProvide a helpful, friendly ZAX response:"
        return base_context
    
    def post(self, request, *args, **kwargs):
        # Extract message and session from the request
        message = request.data.get('message')
        session_id = request.data.get('session_id', 'anonymous')

        if not message:
            self.log_to_terminal(session_id, "", False, error="Message content is required")
            return Response({'error': 'Message content is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if it's a greeting and handle it specially
        if self.is_greeting(message):
            ai_response = self.get_greeting_response()
            response_time = 0.1  # Fast response for greetings
            
            # Log to terminal
            self.log_to_terminal(session_id, message, True, ai_response, response_time=response_time)
            
            # Save chat message
            chat_message = ChatMessage.objects.create(
                user=request.user if request.user.is_authenticated else None,
                session_id=session_id,
                message=message,
                response=ai_response,
                response_time=response_time
            )

            return Response({
                'message': message,
                'response': ai_response,
                'session_id': session_id,
                'timestamp': chat_message.timestamp,
                'response_time': response_time
            })

        try:
            # Interact with OpenAI API
            start_time = time.time()
            
            # Create flexible context
            is_greeting_msg = self.is_greeting(message)
            context_prompt = self.get_flexible_context_prompt(message, is_greeting_msg)
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are ZAX, a helpful AI assistant for the Zambia Revenue Authority (ZRA). Be concise, professional, and informative. Keep responses under 150 words."},
                    {"role": "user", "content": context_prompt}
                ],
                max_tokens=200,  # Reduced for faster responses
                temperature=0.3  # Lower temperature for faster, more focused responses
            )
            end_time = time.time()

            # Parse response and calculate response time
            ai_response = response.choices[0].message.content.strip()
            response_time = end_time - start_time

            # Log successful interaction to terminal
            self.log_to_terminal(session_id, message, True, ai_response, response_time=response_time)

            # Save chat message
            chat_message = ChatMessage.objects.create(
                user=request.user if request.user.is_authenticated else None,
                session_id=session_id,
                message=message,
                response=ai_response,
                response_time=response_time
            )

            # Return the response
            return Response({
                'message': message,
                'response': ai_response,
                'session_id': session_id,
                'timestamp': chat_message.timestamp,
                'response_time': response_time
            })
            
        except Exception as e:
            error_message = str(e)
            
            # Log error to terminal
            self.log_to_terminal(session_id, message, False, error=error_message)
            
            logger.error(f"Error in chatbot API for session {session_id}: {error_message}")
            return Response({
                'error': 'Sorry, I encountered an error processing your request. Please try again.',
                'details': error_message if settings.DEBUG else None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request, *args, **kwargs):
        # Return last 10 chat messages for the session
        session_id = request.query_params.get('session_id', 'anonymous')
        chat_history = ChatMessage.objects.filter(session_id=session_id).order_by('-timestamp')[:10]
        return Response({
            'session_id': session_id,
            'chat_history': [
                {
                    'message': chat.message,
                    'response': chat.response,
                    'timestamp': chat.timestamp
                } for chat in chat_history
            ]
        })