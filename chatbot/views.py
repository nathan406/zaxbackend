from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from .models import ChatMessage, UploadedFile
from .serializers import UploadedFileSerializer
from openai import OpenAI
import time
import logging
import requests
from bs4 import BeautifulSoup
import re
from django.db import connection
from django.core.exceptions import ImproperlyConfigured
import os
from rest_framework.decorators import api_view
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import parser_classes
from rest_framework.permissions import AllowAny
from rest_framework.decorators import permission_classes

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
        
        print(f"\\n{'='*80}")
        print(f"[{timestamp}] CHAT INTERACTION {status_symbol}")
        print(f"Session: {session_id}")
        print(f"Status: {'SUCCESS' if success else 'ERROR'}")
        print(f"{'='*80}")
        
        print(f"👤 USER MESSAGE:")
        print(f"   {user_message}")
        
        if ai_response:
            print(f"\\n🤖 AI RESPONSE:")
            print(f"   {ai_response[:200]}{'...' if len(ai_response) > 200 else ''}")
        
        if error:
            print(f"\\n❌ ERROR:")
            print(f"   {error}")
        
        if response_time:
            print(f"\\n⏱️  RESPONSE TIME: {response_time:.2f}s")
        
        print(f"{'='*80}\\n")
        
    def is_greeting(self, message):
        """Check if the message is a simple greeting (not a specific help request)"""
        message_lower = message.lower().strip()
        
        # Simple greetings only - no specific requests
        simple_greetings = [
            r'^(hi|hello|hey|greetings)$',
            r'^(hi|hello|hey|greetings)\\s*[.!]*$',
            r'^good\\s+(morning|afternoon|evening)$',
            r'^(how are you|what\\'s up|whats up|sup)$',
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

        base_context += f"\\nUser Question: {user_message}\\n\\nProvide a helpful, friendly ZAX response:"
        return base_context
    
    def post(self, request, *args, **kwargs):
        # Extract message and session from the request
        message = request.data.get('message')
        session_id = request.data.get('session_id', 'anonymous')

        if not message:
            self.log_to_terminal(session_id, "", False, error="Message content is required")
            return Response({'error': 'Message content is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if it's a greeting and handle it specially
        # Only show full greeting for new/first-time sessions
        if self.is_greeting(message):
            # Check if this is likely a new session by checking recent messages
            try:
                recent_messages = ChatMessage.objects.filter(session_id=session_id).order_by('-timestamp')[:1]
                is_first_message = len(recent_messages) == 0
            except Exception:
                is_first_message = True  # If DB query fails, assume it's first message
                
            if is_first_message:
                ai_response = self.get_greeting_response()
            else:
                # For repeated greetings in ongoing conversations, give a brief friendly response
                ai_response = "Hello again! How can I assist you with your ZRA matters today? 😊"
            
            response_time = 0.1  # Fast response for greetings
            
            # Log to terminal
            self.log_to_terminal(session_id, message, True, ai_response, response_time=response_time)
            
            # Save chat message (with database safety)
            try:
                chat_message = ChatMessage.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    session_id=session_id,
                    message=message,
                    response=ai_response,
                    response_time=response_time
                )
                timestamp = chat_message.timestamp
            except Exception as db_error:
                logger.warning(f"Could not save to database: {db_error}")
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

            return Response({
                'message': message,
                'response': ai_response,
                'session_id': session_id,
                'timestamp': timestamp,
                'response_time': response_time
            })

        # Get any uploaded files for this session
        file_context = ""
        image_results = []
        latest_message = None  # Initialize to make it accessible later
        
        try:
            latest_message = ChatMessage.objects.filter(session_id=session_id).order_by('-timestamp').first()
            if latest_message:
                uploaded_files = latest_message.uploaded_files.all()
                file_contents = []
                
                for uploaded_file in uploaded_files:
                    file_path = os.path.join(settings.MEDIA_ROOT, uploaded_file.file.name)
                    if os.path.exists(file_path):
                        if uploaded_file.file_type == 'image':
                            # Process images with OpenAI's vision API
                            vision_result = process_image_with_openai(self, file_path, session_id)
                            image_results.append(f"Image: {uploaded_file.original_filename}\\nAnalysis: {vision_result[:1000]}...")  # Limit content to avoid token issues
                            
                            # Update the uploaded file with vision analysis
                            uploaded_file.processed_content = vision_result
                            uploaded_file.processed = True
                            uploaded_file.save()
                        else:
                            # Extract text content from document files
                            text_content = extract_text_from_file(file_path, uploaded_file.file_type)
                            if text_content and len(text_content.strip()) > 0:
                                file_contents.append(f"File: {uploaded_file.original_filename}\\nContent: {text_content[:1000]}...")  # Limit content to avoid token issues

                # Combine all file content
                all_file_contents = file_contents + image_results
                if all_file_contents:
                    file_context = "\\n\\nAdditional context from uploaded files:\\n" + "\\n".join(all_file_contents)
        except Exception as e:
            logger.error(f"Error processing uploaded files for session {session_id}: {e}")
            file_context = ""

        try:
            # Interact with OpenAI API
            start_time = time.time()
            
            # Create flexible context
            is_greeting_msg = self.is_greeting(message)
            base_context = self.get_flexible_context_prompt(message, is_greeting_msg)
            
            # When files are present, the context is about document analysis, not topic redirection
            if file_context:
                # Modify the base context to indicate document analysis context
                base_context = base_context.replace(
                    "For completely unrelated topics, politely say: \"I specialize in ZRA and tax-related matters. While I'd love to chat about other topics, I'm here to help you with tax questions, filing procedures, and ZRA services. Is there anything tax-related I can assist you with?\"",
                    "When analyzing user documents, provide insights related to ZRA services and tax matters based on the document content."
                )
            
            context_prompt = base_context + file_context
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are ZAX, a helpful AI assistant for the Zambia Revenue Authority (ZRA). Be concise, professional, and informative. Keep responses under 150 words. Do not use generic phrases like 'Next Steps:' unless you actually provide specific next steps. Make sure any suggested follow-up actions are genuinely relevant to the user's query. Avoid repeating greeting phrases like 'Hello!' in your responses if the conversation is already ongoing. Never use 'their' instead say 'our' when referring to ZRA services."},
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

            # Save chat message (with database safety)
            try:
                chat_message = ChatMessage.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    session_id=session_id,
                    message=message,
                    response=ai_response,
                    response_time=response_time
                )
                timestamp = chat_message.timestamp
            except Exception as db_error:
                logger.warning(f"Could not save to database: {db_error}")
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

            # Generate dynamic follow-up suggestions based on response content
            follow_up_suggestions = self.generate_follow_up_suggestions(ai_response)
            
            # Get uploaded files for this message to include in response
            uploaded_files_data = []
            try:
                if 'chat_message' in locals():
                    uploaded_files = chat_message.uploaded_files.all()
                    uploaded_files_data = [
                        {
                            'id': f.id,
                            'original_filename': f.original_filename,
                            'file_type': f.file_type,
                            'file_size': f.file_size,
                            'upload_time': f.upload_time.isoformat(),
                            'processed_content': f.processed_content if hasattr(f, 'processed_content') else '',
                            'processed': f.processed if hasattr(f, 'processed') else False
                        }
                        for f in uploaded_files
                    ]
            except Exception as e:
                logger.warning(f"Could not fetch uploaded files for response: {e}")
            
            # Return the response
            return Response({
                'message': message,
                'response': ai_response,
                'session_id': session_id,
                'timestamp': timestamp,
                'response_time': response_time,
                'follow_up_suggestions': follow_up_suggestions,
                'uploaded_files': uploaded_files_data
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

    def options(self, request, *args, **kwargs):
        """Handle CORS preflight requests"""
        response = Response()
        response['Access-Control-Allow-Origin'] = 'https://zrabot.netlify.app'
        response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
    
    def get(self, request, *args, **kwargs):
        # Return last 10 chat messages for the session (with database safety)
        session_id = request.query_params.get('session_id', 'anonymous')
        try:
            chat_history = ChatMessage.objects.filter(session_id=session_id).order_by('-timestamp')[:10]
            history_data = [
                {
                    'message': chat.message,
                    'response': chat.response,
                    'timestamp': chat.timestamp
                } for chat in chat_history
            ]
        except Exception as db_error:
            logger.warning(f"Could not fetch chat history: {db_error}")
            history_data = []
        
        return Response({
            'session_id': session_id,
            'chat_history': history_data
        })
    
    def generate_follow_up_suggestions(self, response_text):
        """Generate dynamic follow-up suggestions based on response content"""
        response_lower = response_text.lower()
        suggestions = []
        
        # Registration-related suggestions (more specific match)
        if any(term in response_lower for term in ['register', 'registration', 'tpin', 'business']):
            if not any(term in response_lower for term in ['what is', 'what\\'s', 'define', 'meaning of']):
                # More specific to the registration context
                if 'who' in response_lower or 'individual' in response_lower or 'entity' in response_lower:
                    suggestions.extend([
                        {"question": "Legal age for registration", "action": "registration-age"},
                        {"question": "Required documents", "action": "required-docs"}
                    ])
                else:
                    suggestions.extend([
                        {"question": "How to register?", "action": "registration-process"},
                        {"question": "Required documents", "action": "required-docs"}
                    ])
        
        # Tax-related suggestions (avoid if it's just explaining what something is)
        if any(term in response_lower for term in ['tax', 'vat', 'paye', 'income tax', 'corporate tax']):
            # Don't suggest follow-ups if the response is just explaining what something is
            if not any(term in response_lower for term in ['what is', 'what\\'s', 'define', 'meaning of']):
                if 'vat' in response_lower and 'registration' in response_lower:
                    suggestions.extend([
                        {"question": "How to register for VAT?", "action": "vat-registration"},
                        {"question": "VAT filing requirements", "action": "vat-filing"}
                    ])
                else:
                    suggestions.extend([
                        {"question": "Tax payment methods", "action": "payment-methods"},
                        {"question": "Tax filing deadlines", "action": "tax-deadlines"}
                    ])
        # Continue with rest of the method...
        # Contact/service-related suggestions
        if any(term in response_lower for term in ['contact', 'reach', 'office', 'location', 'call']):
            suggestions.extend([
                {"question": "ZRA office locations", "action": "office-locations"},
                {"question": "Contact ZRA", "action": "contact-info"}
            ])
        
        # Payment-related suggestions (only if clearly related to payment)
        if any(term in response_lower for term in ['pay', 'payment', 'fee', 'amount due']):
            suggestions.extend([
                {"question": "Payment methods", "action": "payment-options"},
                {"question": "Online payment", "action": "online-payment"}
            ])
        
        # Remove duplicates and return top 2 suggestions
        seen_questions = set()
        unique_suggestions = []
        for suggestion in suggestions:
            if suggestion["question"] not in seen_questions:
                unique_suggestions.append(suggestion)
                seen_questions.add(suggestion["question"])
        
        return unique_suggestions[:2]


@permission_classes([AllowAny])
class FileUploadView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    
    def post(self, request, *args, **kwargs):
        # Get session_id from request data
        session_id = request.data.get('session_id', 'anonymous')
        
        # Get the latest chat message for this session to associate the file with
        try:
            # Try to get the latest user message in this session
            latest_message = ChatMessage.objects.filter(
                session_id=session_id
            ).order_by('-timestamp').first()
        except Exception as e:
            logger.error(f"Could not fetch latest message for session {session_id}: {e}")
            latest_message = None
        
        # If no message exists, we'll create a placeholder
        if not latest_message:
            # Create a placeholder message to associate with the file
            latest_message = ChatMessage.objects.create(
                session_id=session_id,
                message="File uploaded",
                response="File processing...",
                response_time=0.1
            )
        
        # Process uploaded files
        uploaded_files = []
        for file in request.FILES.getlist('files'):
            # Create UploadedFile instance
            uploaded_file = UploadedFile.objects.create(
                chat_message=latest_message,
                file=file,
                original_filename=file.name
            )
            uploaded_files.append(uploaded_file)
        
        # If user is connected to staff, also create a notification in the active staff chat
        from .models import ActiveChatSession, RealTimeChatMessage
        try:
            active_session = ActiveChatSession.objects.filter(
                session_id=session_id,
                status__in=['active', 'pending']
            ).first()
            
            if active_session:
                # Create a system message about the file upload in the staff chat
                RealTimeChatMessage.objects.create(
                    chat_session=active_session,
                    sender_type='system',  # System message about file upload
                    sender_id='system',
                    message=f"User uploaded {len(uploaded_files)} file(s): {', '.join([f.original_filename for f in uploaded_files])}"
                )
        except Exception as e:
            logger.error(f"Error creating staff notification for file upload: {e}")
        
        # Serialize the uploaded files
        serializer = UploadedFileSerializer(uploaded_files, many=True)
        
        return Response({
            'message': f'Successfully uploaded {len(uploaded_files)} file(s)',
            'files': serializer.data,
            'session_id': session_id
        }, status=status.HTTP_201_CREATED)


def process_image_with_openai(chatbot_view, image_path, session_id):
    """
    Process image using OpenAI's vision capabilities
    """
    try:
        import base64
        from openai import OpenAI
        
        # Read and encode the image
        with open(image_path, "rb") as img_file:
            base64_image = base64.b64encode(img_file.read()).decode('utf-8')
        
        # Create a new OpenAI client for vision processing
        client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=15.0  # Slightly longer timeout for vision processing
        )
        
        # Process the image with OpenAI's vision model
        response = client.chat.completions.create(
            model="gpt-4o",  # Using current vision-capable model
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this image and describe any text, numbers, or information visible in it. Focus on details that might be relevant for tax or ZRA-related purposes. If there are documents, forms, receipts, or any financial information, please transcribe and summarize the key details."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500
        )
        
        # Extract the response
        vision_result = response.choices[0].message.content
        logger.info(f"Vision API processed image for session {session_id}: {image_path}")
        return vision_result
    except Exception as e:
        logger.error(f"Error processing image with OpenAI Vision for {image_path}: {e}")
        return f"[Image file uploaded: {os.path.basename(image_path)} - Could not analyze content with vision API]"

def extract_text_from_file(file_path, file_type):
    """
    Extract text from different file types
    """
    import mimetypes
    mime_type, _ = mimetypes.guess_type(file_path)
    
    try:
        if file_type == 'image' or (mime_type and mime_type.startswith('image/')):
            # For now, return a placeholder that indicates this is an image
            # The actual image processing will be handled separately with OpenAI vision
            return f"[Image file uploaded: {os.path.basename(file_path)} - To be processed with vision API]"
        elif file_path.lower().endswith('.pdf'):
            # For PDF files, we can extract text using PyPDF2
            import PyPDF2
            with open(file_path, 'rb') as pdf_file:
                reader = PyPDF2.PdfReader(pdf_file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\\n"
            return text if text.strip() else f"[PDF file: {os.path.basename(file_path)} - could not extract text]"
        elif file_path.lower().endswith(('.txt', '.md')):
            # For text files
            with open(file_path, 'r', encoding='utf-8') as text_file:
                return text_file.read()
        elif file_path.lower().endswith(('.docx', '.doc')):
            # For Word documents
            from docx import Document
            doc = Document(file_path)
            text = '\\n'.join([paragraph.text for paragraph in doc.paragraphs])
            return text if text.strip() else f"[DOC file: {os.path.basename(file_path)} - could not extract text]"
        else:
            # For other file types, return a placeholder
            return f"[File uploaded: {os.path.basename(file_path)}, type: {file_type}]"
    except Exception as e:
        logger.error(f"Error extracting text from {file_path}: {e}")
        return f"[Error reading file: {os.path.basename(file_path)} - {str(e)}]"