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
        if not message:
            return False

        message_lower = message.lower().strip()

        # Quick, permissive greeting detection: check first token or startswith common greetings
        greetings = ['hi', 'hello', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
        first_word = message_lower.split()[0]
        if first_word in greetings or any(message_lower.startswith(g + ' ') or message_lower == g for g in greetings):
            # If the message also contains ZRA/tax keywords, treat it as not just a greeting
            if self.is_zra_related(message):
                return False
            return True

        # Fallback to pattern matching for other short, casual phrases
        simple_patterns = [r'^(how are you|what\'s up|whats up|sup)$', r'^(help|assist|support)$', r'^can you help$', r'^(start|begin|getting started)$']
        for pattern in simple_patterns:
            if re.search(pattern, message_lower):
                if self.is_zra_related(message):
                    return False
                return True

        return False
        
    def is_zra_related(self, message):
        """Check if the message is related to ZRA/tax matters"""
        zra_keywords = [
            'tax', 'zra', 'zambia revenue authority', 'vat', 'paye', 'income tax',
            'corporate tax', 'customs', 'excise', 'duty', 'filing', 'return',
            'registration', 'tpin', 'withholding', 'penalty', 'compliance',
            'revenue', 'taxation', 'levy', 'assessment', 'audit', 'refund',
            'business', 'company', 'individual', 'taxpayer', 'declaration',
            'payment', 'deadline', 'form', 'certificate', 'license',
            'zambia', 'tpin', 'itr', 'tin', 'turnover tax', 'presumptive tax',
            'withholding tax', 'pay as you earn', 'value added tax',
            'paye', 'pay as you earn', 'employment tax', 'salary tax',
            'corporate income tax', 'cit', 'business tax', 'trade license',
            'import duty', 'export duty', 'customs clearance',
            'tax clearance', 'compliance certificate', 'tax certificate',
            'vat registration', 'tpin application', 'tax audit',
            'tax investigation', 'tax dispute', 'appeal', 'objection',
            'tax refund', 'restitution', 'tax credit', 'deduction',
            'tax return', 'itr', 'income tax return', 'annual return',
            'monthly return', 'quarterly return', 'vat return',
            'paye return', 'withholding tax return', 'fringe benefits',
            'benefit in kind', 'perquisite', 'allowance', 'bonus',
            'commission', 'overtime', 'severance', 'gratuity',
            'capital gains', 'property tax', 'rental income',
            'investment income', 'dividend', 'interest', 'royalty',
            'licensing', 'permit', 'authorization', 'exemption',
            'relief', 'rebate', 'discount', 'adjustment', 'amendment'
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

        # Initialize file context placeholder (will be filled from uploaded files below)
        file_context = ""
        # File processing happens below; defer validation of message until after files are processed

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
                    # Skip any files that have already been processed to avoid re-processing and resend loops
                    if getattr(uploaded_file, 'processed', False):
                        logger.info(f"Skipping already-processed file {uploaded_file.original_filename} for session {session_id}")
                        continue
                    file_path = os.path.join(settings.MEDIA_ROOT, uploaded_file.file.name)
                    logger.info(f"Processing file {uploaded_file.original_filename} of type {uploaded_file.file_type} for session {session_id}")
                    # Log the actual file extension to help with debugging
                    import mimetypes
                    mime_type, _ = mimetypes.guess_type(file_path)
                    logger.info(f"File MIME type for {uploaded_file.original_filename}: {mime_type}")
                    if os.path.exists(file_path):
                        # Log file size for debugging
                        file_size = os.path.getsize(file_path)
                        logger.info(f"File {uploaded_file.original_filename} size: {file_size} bytes")
                        if file_size == 0:
                            logger.warning(f"File {uploaded_file.original_filename} is empty")
                            if uploaded_file.file_type == 'image':
                                image_results.append(f"Image: {uploaded_file.original_filename}\\nError: File is empty (0 bytes)")
                            else:
                                file_contents.append(f"File: {uploaded_file.original_filename}\\nContent: [File is empty]")
                            continue
                        if uploaded_file.file_type == 'image':
                            # Process images with OpenAI's vision API
                            logger.info(f"Sending image {uploaded_file.original_filename} to OpenAI Vision API")
                            try:
                                vision_result = process_image_with_openai(self, file_path, session_id)
                                logger.info(f"Received vision result for {uploaded_file.original_filename}: {len(vision_result) if vision_result else 0} characters")
                                # Log a preview of the vision result for debugging
                                if vision_result:
                                    logger.debug(f"Vision result preview for {uploaded_file.original_filename}: {vision_result[:200]}...")
                                    # Check if the vision result contains meaningful content
                                    if len(vision_result.strip()) > 50 and not vision_result.startswith("[Image file uploaded"):
                                        image_results.append(f"Image: {uploaded_file.original_filename}\\nAnalysis: {vision_result[:1000]}...")  # Limit content to avoid token issues
                                    else:
                                        logger.info(f"Vision result for {uploaded_file.original_filename} appears to be an error or empty")
                                        image_results.append(f"Image: {uploaded_file.original_filename}\\nAnalysis: [Could not extract meaningful content from image]")
                                else:
                                    logger.warning(f"No vision result returned for {uploaded_file.original_filename}")
                                    image_results.append(f"Image: {uploaded_file.original_filename}\\nAnalysis: [No content could be extracted from image]")
                                
                                # Update the uploaded file with vision analysis
                                uploaded_file.processed_content = vision_result
                                uploaded_file.processed = True
                                uploaded_file.save()
                            except Exception as process_error:
                                logger.error(f"Error processing image {uploaded_file.original_filename}: {process_error}")
                                image_results.append(f"Image: {uploaded_file.original_filename}\\nError: Failed to process image with vision API")
                        else:
                            # Extract text content from document files
                            logger.info(f"Extracting text from document {uploaded_file.original_filename}")
                            try:
                                text_content = extract_text_from_file(file_path, uploaded_file.file_type, session_id)
                                if text_content and len(text_content.strip()) > 0:
                                    logger.info(f"Extracted text from {uploaded_file.original_filename}: {len(text_content)} characters")
                                    # Log a preview of the extracted text for debugging
                                    logger.debug(f"Text content preview for {uploaded_file.original_filename}: {text_content[:200]}...")
                                    file_contents.append(f"File: {uploaded_file.original_filename}\\nContent: {text_content[:1000]}...")  # Limit content to avoid token issues
                                    # Mark the uploaded file as processed and save extracted content to avoid reprocessing
                                    try:
                                        uploaded_file.processed_content = text_content
                                        uploaded_file.processed = True
                                        uploaded_file.save()
                                    except Exception as save_err:
                                        logger.warning(f"Could not mark uploaded file as processed: {save_err}")
                                else:
                                    logger.info(f"No text content extracted from {uploaded_file.original_filename}")
                                    file_contents.append(f"File: {uploaded_file.original_filename}\\nContent: [No text content could be extracted]")
                            except Exception as extract_error:
                                logger.error(f"Error extracting text from {uploaded_file.original_filename}: {extract_error}")
                                file_contents.append(f"File: {uploaded_file.original_filename}\\nContent: [Error extracting text from file]")
                    else:
                        logger.warning(f"File not found: {file_path}")
                        if uploaded_file.file_type == 'image':
                            image_results.append(f"Image: {uploaded_file.original_filename}\\nError: File not found at {file_path}")
                        else:
                            file_contents.append(f"File: {uploaded_file.original_filename}\\nContent: [File not found at {file_path}]")

                # Combine all file content
                all_file_contents = file_contents + image_results
                logger.info(f"Combining file contents for session {session_id}: {len(file_contents)} text files, {len(image_results)} images, total {len(all_file_contents)} items")
                # Log sample of what we're combining
                if file_contents:
                    logger.debug(f"Sample text file contents: {file_contents[0][:200] if file_contents else 'None'}...")
                if image_results:
                    logger.debug(f"Sample image results: {image_results[0][:200] if image_results else 'None'}...")
                if all_file_contents:
                    file_context = "\\n\\nAdditional context from uploaded files (analyze these documents for ZRA-related content):\\n" + "\\n".join(all_file_contents)
                    # Detect if the extracted content contains ZRA-related keywords and mark it to guide the model
                    try:
                        combined_text_preview = ' '.join(all_file_contents).lower()
                        if self.is_zra_related(combined_text_preview):
                            file_context = "\\n\\n[NOTE: Uploaded documents appear to contain ZRA/tax-related content. Please analyze accordingly.]\\n" + file_context
                            logger.info(f"Marked uploaded files as ZRA-related for session {session_id}")
                    except Exception:
                        logger.debug("Could not reliably determine whether uploaded files are ZRA-related")

                    logger.info(f"Built file context for session {session_id}: {len(all_file_contents)} files processed")
                    logger.debug(f"File context content preview: {file_context[:500]}...")
                else:
                    logger.info(f"No file content extracted for session {session_id}")
                    # Even if no content was extracted, we should still indicate that files were uploaded
                    if uploaded_files:
                        file_names = [f.original_filename for f in uploaded_files]
                        file_context = f"\\n\\nUser uploaded {len(uploaded_files)} file(s): {', '.join(file_names)}. Please analyze these files for ZRA-related content."
                        logger.info(f"Created placeholder file context for {len(uploaded_files)} files")
        except Exception as e:
            logger.error(f"Error processing uploaded files for session {session_id}: {e}")
            file_context = ""
            
        # If files are present but no message was provided, create a default analysis prompt
        if file_context and not message:
            message = "Please analyze the uploaded documents and provide insights related to ZRA and tax matters."

        # If after processing we still have neither message nor file context, reject the request
        if not message and not file_context:
            self.log_to_terminal(session_id, "", False, error="Message content is required")
            return Response({'error': 'Message content is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Interact with OpenAI API
            start_time = time.time()
            
            # Create flexible context
            is_greeting_msg = self.is_greeting(message)
            base_context = self.get_flexible_context_prompt(message, is_greeting_msg)
            
            # Log the base context for debugging
            logger.debug(f"Base context for session {session_id}: {len(base_context)} characters")

            # Log file context presence and a preview for easier debugging of document handling
            try:
                logger.info(f"File context present for session {session_id}: {bool(file_context)}")
                if file_context:
                    logger.info(f"File context preview for session {session_id}: {file_context[:500]}")
                    # Also log a lightweight keyword detection result
                    try:
                        zra_flag = self.is_zra_related(file_context.lower())
                        logger.info(f"Lightweight ZRA keyword detection for session {session_id}: {zra_flag}")
                    except Exception:
                        logger.debug("Could not run lightweight ZRA detection on file_context")
            except Exception:
                logger.debug("Could not log file context preview")
            
            # When files are present, the context is about document analysis
            if file_context:
                # Modify the base context to indicate document analysis context
                # Tell the AI to treat the document content as the primary focus, regardless of initial message topic
                base_context = base_context.replace(
                    "For completely unrelated topics, politely say: \"I specialize in ZRA and tax-related matters. While I'd love to chat about other topics, I'm here to help you with tax questions, filing procedures, and ZRA services. Is there anything tax-related I can assist you with?\"",
                    "When analyzing user documents, provide insights related to ZRA services and tax matters based on the document content. Treat the document content as the primary context for your response, regardless of the user's initial message. If the document contains ZRA-related information, analyze and explain it. If it contains questions or requests, address those specifically. Always analyze uploaded documents for ZRA-related content, even if the initial user message seems unrelated."
                )
                logger.info(f"Modified base context for file analysis in session {session_id}")
            
            context_prompt = base_context + file_context
            
            # Log the context being sent to AI for debugging
            logger.debug(f"Context prompt for session {session_id}: {len(context_prompt)} characters")
            if len(context_prompt) > 500:
                logger.debug(f"Context prompt preview: {context_prompt[:500]}...")
            else:
                logger.debug(f"Full context prompt: {context_prompt}")
            
            # If files are present, make sure the AI knows to focus on document analysis
            # Also, if the user didn't provide a message but uploaded files, treat the files as the main query
            if file_context and (not message or message.strip() == ""):
                context_prompt += "\\n\\nIMPORTANT: The user has uploaded documents without a specific message. Your primary task is to ANALYZE THE CONTENT OF THESE DOCUMENTS and provide a detailed response about what you find. Focus on the document content, not the user's initial message. If the documents contain ZRA-related information, explain that information in detail. If they contain questions or requests, answer those specifically. If the documents do NOT contain ZRA-related content, respond with: 'I specialize in ZRA and tax-related matters. While I'd love to help with other topics, I can only assist with tax questions, filing procedures, and ZRA services. Please upload ZRA-related documents or ask tax-related questions.' Provide a comprehensive analysis of the document content. DO NOT IGNORE THE DOCUMENTS!"
            elif file_context:
                context_prompt += "\\n\\nIMPORTANT: The user has uploaded documents. Your primary task is to ANALYZE THE CONTENT OF THESE DOCUMENTS and provide a detailed response about what you find. Focus on the document content, not the user's initial message. If the documents contain ZRA-related information, explain that information in detail. If they contain questions or requests, answer those specifically. If the documents do NOT contain ZRA-related content, respond with: 'I specialize in ZRA and tax-related matters. While I'd love to help with other topics, I can only assist with tax questions, filing procedures, and ZRA services. Please upload ZRA-related documents or ask tax-related questions.' Provide a comprehensive analysis of the document content. DO NOT IGNORE THE DOCUMENTS!"
            
            # Stronger system instruction: prefer document analysis when uploaded files contain ZRA keywords
            system_prompt = (
                "You are ZAX, a helpful AI assistant for the Zambia Revenue Authority (ZRA). Be concise, professional, and informative. "
                "Keep responses under 150 words. Do not use generic phrases like 'Next Steps:' unless you actually provide specific next steps. "
                "Make sure any suggested follow-up actions are genuinely relevant to the user's query. Avoid repeating greeting phrases like 'Hello!' in your responses if the conversation is already ongoing. "
                "Never use 'their' — instead say 'our' when referring to ZRA services. "
                "When user-uploaded documents are present, treat the uploaded documents as the primary context. "
                "If the uploaded documents or the provided file context contain ZRA/tax-related keywords, PRIORITIZE analyzing those documents and produce a ZRA-specific answer. "
                "Only use the generic fallback line about specializing in ZRA if there is NO evidence of ZRA/tax content in the uploaded documents or message. "
                "When analyzing user-uploaded documents, provide insights based on what you see in the document. If the documents contain questions or requests, answer those specifically. "
                "If the documents do not contain ZRA-related content, politely inform the user that you specialize in ZRA and tax-related matters and can only assist with tax questions, filing procedures, and ZRA services."
            )

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context_prompt}
                ],
                max_tokens=400,  # increase to give model more room to analyze documents
                temperature=0.2  # Lower temperature for focused responses
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
            import traceback
            tb = traceback.format_exc()
            error_message = str(e)

            # Log full exception with traceback
            logger.exception(f"Error in chatbot API for session {session_id}: {error_message}\n{tb}")

            # Log error to terminal with concise message
            self.log_to_terminal(session_id, message, False, error=error_message)

            # Return safe error response; include details when DEBUG is enabled
            return Response({
                'error': 'Sorry, I encountered an error processing your request. Please try again.',
                'details': error_message if settings.DEBUG else None,
                'traceback': tb if settings.DEBUG else None
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
            if not any(term in response_lower for term in ["what is", "what's", 'define', 'meaning of']):
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
            if not any(term in response_lower for term in ["what is", "what's", 'define', 'meaning of']):
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

        # Extract the response and ensure it's a string
        vision_result = response.choices[0].message.content
        try:
            # Some SDK responses may not be plain strings; cast to str to be safe
            vision_result = str(vision_result)
        except Exception:
            pass
        logger.info(f"Vision API processed image for session {session_id}: {image_path}")
        return vision_result
    except Exception as e:
        logger.error(f"Error processing image with OpenAI Vision for {image_path}: {e}")
        return f"[Image file uploaded: {os.path.basename(image_path)} - Could not analyze content with vision API]"


def send_image_bytes_to_openai(image_bytes, session_id):
    """Send image bytes to OpenAI Vision and return the text analysis as a string."""
    try:
        import base64
        from openai import OpenAI

        client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=15.0)
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this image and transcribe any text or numbers visible. Focus on details relevant to tax or ZRA matters. If this is a document, summarize key fields like names, TPIN, amounts, dates, and references."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                        }
                    ]
                }
            ],
            max_tokens=800,
            temperature=0.1
        )

        vision_text = response.choices[0].message.content
        try:
            vision_text = str(vision_text)
        except Exception:
            pass
        return vision_text
    except Exception as e:
        logger.error(f"Error sending image bytes to OpenAI for session {session_id}: {e}")
        return ""


def process_pdf_with_openai(pdf_path, session_id):
    """Render PDF pages to images using PyMuPDF and send each page to OpenAI Vision. Return combined text."""
    try:
        import fitz  # PyMuPDF
        from io import BytesIO

        doc = fitz.open(pdf_path)
        page_texts = []
        for page_num in range(len(doc)):
            try:
                page = doc.load_page(page_num)
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                vision_result = send_image_bytes_to_openai(img_bytes, session_id)
                if vision_result:
                    page_texts.append(vision_result)
            except Exception as page_err:
                logger.debug(f"Error rendering or sending PDF page {page_num} to OpenAI: {page_err}")

        combined = "\n\n".join(page_texts)
        return combined if combined.strip() else ""
    except Exception as e:
        logger.error(f"PyMuPDF/OpenAI fallback failed for {pdf_path}: {e}")
        return ""

def extract_text_from_file(file_path, file_type, session_id=None):
    """
    Extract text from different file types with robust fallbacks.
    Attempts local OCR first (pytesseract), then pdfplumber OCR for PDFs, and finally OpenAI Vision when local methods fail.
    """
    import mimetypes
    mime_type, _ = mimetypes.guess_type(file_path)

    try:
        # IMAGE: try local OCR, then OpenAI Vision fallback
        if file_type == 'image' or (mime_type and mime_type.startswith('image/')):
            try:
                from PIL import Image
                import pytesseract

                logger.info(f"Running local OCR on image {file_path}")
                img = Image.open(file_path).convert('RGB')
                ocr_text = pytesseract.image_to_string(img)
                if ocr_text and ocr_text.strip():
                    return ocr_text
                logger.info(f"Local OCR returned no text for image {file_path}")
            except Exception as ocr_err:
                logger.debug(f"Local OCR failed for {file_path}: {ocr_err}")

            # OpenAI Vision fallback
            try:
                logger.info(f"Falling back to OpenAI Vision for image {file_path}")
                vision_result = process_image_with_openai(None, file_path, session_id or 'unknown')
                if vision_result and vision_result.strip():
                    return vision_result
            except Exception as openai_img_err:
                logger.debug(f"OpenAI Vision fallback failed for image {file_path}: {openai_img_err}")

            return f"[Image file uploaded: {os.path.basename(file_path)} - Could not extract text]"

        # PDF: try PyPDF2 text extraction, then pdfplumber+pytesseract OCR, then OpenAI PDF fallback
        if file_path.lower().endswith('.pdf'):
            try:
                import PyPDF2
                with open(file_path, 'rb') as pdf_file:
                    reader = PyPDF2.PdfReader(pdf_file)
                    text = ""
                    for page in reader.pages:
                        try:
                            page_text = page.extract_text() or ""
                        except Exception:
                            page_text = ""
                        if page_text:
                            text += page_text + "\n"

                if text and text.strip():
                    return text
            except Exception as pdf_err:
                logger.debug(f"PyPDF2 extraction failed for {file_path}: {pdf_err}")

            # Try pdfplumber + pytesseract OCR
            try:
                import pdfplumber
                import pytesseract
                from PIL import Image

                logger.info(f"Attempting OCR on scanned PDF {file_path} using pdfplumber + pytesseract")
                ocr_text = ""
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        try:
                            page_text = page.extract_text() or ""
                            if page_text and page_text.strip():
                                ocr_text += page_text + "\n"
                                continue

                            # Render page as image and OCR
                            page_image = page.to_image(resolution=150)
                            pil_img = page_image.original
                            if pil_img:
                                page_ocr = pytesseract.image_to_string(pil_img)
                                if page_ocr and page_ocr.strip():
                                    ocr_text += page_ocr + "\n"
                        except Exception as page_err:
                            logger.debug(f"Error OCRing page of PDF {file_path}: {page_err}")

                if ocr_text and ocr_text.strip():
                    return ocr_text
            except Exception as ocr_pdf_err:
                logger.debug(f"pdfplumber/pytesseract OCR failed for {file_path}: {ocr_pdf_err}")

            # OpenAI PDF fallback (render pages and send to OpenAI)
            try:
                openai_pdf_text = process_pdf_with_openai(file_path, session_id or 'unknown')
                if openai_pdf_text and openai_pdf_text.strip():
                    return openai_pdf_text
            except Exception as openai_pdf_err:
                logger.debug(f"OpenAI PDF fallback failed for {file_path}: {openai_pdf_err}")

            return f"[PDF file: {os.path.basename(file_path)} - could not extract text]"

        # Text files
        if file_path.lower().endswith(('.txt', '.md')):
            with open(file_path, 'r', encoding='utf-8') as text_file:
                return text_file.read()

        # Word documents
        if file_path.lower().endswith(('.docx', '.doc')):
            from docx import Document
            doc = Document(file_path)
            text = '\n'.join([paragraph.text for paragraph in doc.paragraphs])
            return text if text.strip() else f"[DOC file: {os.path.basename(file_path)} - could not extract text]"

        # Other file types
        return f"[File uploaded: {os.path.basename(file_path)}, type: {file_type}]"

    except Exception as e:
        logger.error(f"Error extracting text from {file_path}: {e}")
        return f"[Error reading file: {os.path.basename(file_path)} - {str(e)}]"