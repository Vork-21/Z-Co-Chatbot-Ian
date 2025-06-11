import json
import sys
import os
import logging
import time
import hmac
import hashlib
import requests
import threading
import random
import string
from datetime import datetime
from flask import Flask, request, jsonify

# Import the enhanced modular components
from config_manager import config
from business_manager_auth import BusinessManagerAuth
# Note: conversation_manager needs to be created based on your existing logic

# Configure comprehensive logging
logger = config.get_logger("MessengerWebhook")
logger.info("=== MessengerWebhook Application Starting ===")

# Initialize Flask application
app = Flask(__name__)

# Initialize authentication handler based on page type
if config.use_business_manager:
    logger.info("Initializing Business Manager authentication")
    auth_handler = BusinessManagerAuth()
else:
    logger.info("Using personal page authentication")
    auth_handler = None

# Active conversation sessions
active_conversations = {}

class MessengerSession:
    """
    Enhanced Messenger session that works with both personal and Business Manager pages.
    """
    
    def __init__(self, sender_id: str):
        self.sender_id = sender_id
        # self.conversation_manager = ConversationManager()  # You'll need to create this
        self.conversation_active = True
        self.last_activity = time.time()
        self.handled_by_agent = False
        
        logger.info(f"New session created for sender {sender_id} (Page type: {'Business Manager' if config.use_business_manager else 'Personal'})")
    
    def process_message(self, message_text: str) -> None:
        """Process user message and generate appropriate response"""
        if not self.conversation_active:
            return
        
        # Update activity timestamp
        self.last_activity = time.time()
        
        # Skip processing if conversation handed off to agent
        if self.handled_by_agent:
            self._send_message("Your message has been received. An agent will respond shortly.")
            return
        
        try:
            # TODO: Replace with your actual conversation manager logic
            # response_data = self.conversation_manager.analyze_response(message_text)
            
            # Placeholder logic - replace with your actual implementation
            response_data = {"message": f"Echo: {message_text}"}
            
            # Handle various response types based on your existing logic
            if 'error' in response_data:
                self._send_message(response_data['error'])
                return
            
            # For now, just echo the message
            self._send_message(f"I received: {message_text}")
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self._send_message("I'm having trouble processing your message. Let me connect you with a live representative.")
            self._transition_to_agent("Error processing message")
    
    def _send_message(self, message_text: str, retry_count: int = 3) -> bool:
        """
        Send message to user via Facebook Messenger API with enhanced Business Manager support
        """
        attempt = 0
        
        while attempt < retry_count:
            try:
                # Get the appropriate access token
                access_token = self._get_access_token()
                if not access_token:
                    logger.error("No access token available")
                    return False
                
                url = "https://graph.facebook.com/v22.0/me/messages"
                payload = {
                    "recipient": {"id": self.sender_id},
                    "message": {"text": message_text},
                    "messaging_type": "RESPONSE"
                }
                params = {"access_token": access_token}
                
                response = requests.post(url, json=payload, params=params, timeout=config.api_timeout)
                
                if response.status_code == 200:
                    return True
                
                # Handle rate limiting with exponential backoff
                error_data = response.json().get('error', {})
                if error_data.get('code') == 4:
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                    time.sleep(wait_time)
                    attempt += 1
                    continue
                
                # Handle Business Manager specific errors
                error_code = error_data.get('code')
                error_message = error_data.get('message', '')
                
                if error_code == 200 and "PAGES_MESSAGING" in error_message:
                    logger.error("Pages messaging permission error - check Business Manager permissions")
                elif error_code == 100 and "business_management" in error_message:
                    logger.error("Business management permission required")
                elif error_code == 283:
                    logger.error("Missing manage_pages permission")
                
                logger.error(f"Failed to send message: {response.text}")
                return False
                
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                attempt += 1
                
        return False
    
    def _get_access_token(self) -> str:
        """Get the appropriate access token based on page type"""
        if config.use_business_manager:
            if auth_handler:
                return auth_handler.get_page_token()
            else:
                logger.error("Business Manager authentication handler not available")
                return ""
        else:
            return config.facebook_page_token
    
    def _transition_to_agent(self, reason: str) -> None:
        """Mark conversation for human agent handling"""
        self.handled_by_agent = True
        logger.info(f"Conversation {self.sender_id} transitioned to agent. Reason: {reason}")
        
        try:
            # Generate case reference ID
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            ref_id = f"{timestamp[-6:]}_{random_suffix}"
            
            # Log case details for manual agent review
            logger.info(f"Case transition details - Ref: #{ref_id}, Reason: {reason}")
            
            # Notify user about agent handoff
            self._send_message(f"Thank you for providing your information. A team member will review your case (Ref: #{ref_id}) and continue this conversation shortly.")
            
        except Exception as e:
            logger.error(f"Error during agent transition: {e}")
            self._send_message("I'll connect you with a representative who can help you further. They'll respond shortly.")
    
    def send_welcome_message(self) -> None:
        """Send initial welcome message to begin conversation"""
        welcome_message = "Hello! I'm here to help you determine if you may have a valid cerebral palsy case. To get started, could you please tell me your child's current age?"
        self._send_message(welcome_message)
        logger.info(f"Sent welcome message to {self.sender_id}")

def verify_facebook_signature(request_data: bytes, signature_header: str) -> bool:
    """Verify request signature from Facebook for security"""
    app_secret = config.facebook_app_secret
    if not app_secret:
        logger.warning("APP_SECRET not configured, skipping signature verification")
        return True
    
    if not signature_header:
        logger.warning("No signature header provided")
        return False
    
    # Parse signature header format: "sha1=<signature>"
    elements = signature_header.split('=')
    if len(elements) != 2:
        logger.warning(f"Invalid signature format: {signature_header}")
        return False
    
    signature = elements[1]
    
    # Calculate expected signature
    expected_signature = hmac.new(
        bytes(app_secret, 'utf-8'),
        msg=request_data,
        digestmod=hashlib.sha1
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)

def cleanup_inactive_sessions():
    """Background thread to clean up inactive conversation sessions"""
    while True:
        try:
            current_time = time.time()
            inactive_threshold = 3600  # 1 hour timeout
            
            to_remove = []
            for sender_id, session in active_conversations.items():
                if current_time - session.last_activity > inactive_threshold:
                    to_remove.append(sender_id)
            
            for sender_id in to_remove:
                logger.info(f"Removing inactive session for {sender_id}")
                del active_conversations[sender_id]
            
            time.sleep(900)  # Check every 15 minutes
        except Exception as e:
            logger.error(f"Error in cleanup thread: {e}")
            time.sleep(900)

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_inactive_sessions, daemon=True)
cleanup_thread.start()

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Handle Facebook webhook verification challenge"""
    mode = request.args.get('hub_mode', '')
    token = request.args.get('hub_verify_token', '')
    challenge = request.args.get('hub_challenge', '')
    
    logger.info(f"Webhook verification attempt - Mode: {mode}, Token provided: {bool(token)}")
    
    if mode == 'subscribe' and token == config.facebook_verify_token:
        logger.info("Webhook verified successfully")
        try:
            return str(int(challenge))
        except ValueError:
            logger.warning(f"Challenge conversion failed, returning as-is: {challenge}")
            return challenge
    
    logger.warning(f"Webhook verification failed - Mode: {mode}")
    return 'Verification Failed', 403

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming Facebook Messenger events"""
    logger.info("=== WEBHOOK POST REQUEST RECEIVED ===")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Content-Type: {request.content_type}")
    logger.info(f"Page type: {'Business Manager' if config.use_business_manager else 'Personal'}")
    
    # Verify request signature
    signature = request.headers.get('X-Hub-Signature', '')
    logger.info(f"Signature header: {signature}")
    
    if not verify_facebook_signature(request.get_data(), signature):
        logger.warning("Invalid request signature")
        return 'Invalid signature', 403
    
    try:
        data = request.json
        if not data or data.get('object') != 'page':
            return 'Not a page subscription', 404
        
        # Process each entry and messaging event
        for entry in data.get('entry', []):
            for messaging_event in entry.get('messaging', []):
                sender_id = messaging_event.get('sender', {}).get('id')
                
                if not sender_id:
                    continue
                
                # Handle text messages
                if 'message' in messaging_event:
                    message_text = messaging_event.get('message', {}).get('text')
                    
                    if not message_text:
                        continue  # Skip non-text messages
                    
                    # Get or create session
                    if sender_id not in active_conversations:
                        active_conversations[sender_id] = MessengerSession(sender_id)
                        active_conversations[sender_id].send_welcome_message()
                    else:
                        active_conversations[sender_id].process_message(message_text)
                
                # Handle postback events (button clicks)
                elif 'postback' in messaging_event:
                    payload = messaging_event.get('postback', {}).get('payload')
                    
                    if not payload:
                        continue
                    
                    # Get or create session
                    if sender_id not in active_conversations:
                        active_conversations[sender_id] = MessengerSession(sender_id)
                    
                    # Process postback as text message
                    active_conversations[sender_id].process_message(payload)
        
        return 'Success', 200
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return 'Internal Server Error', 500

@app.route('/', methods=['GET'])
def home():
    """Health check endpoint"""
    return {
        'status': 'CP Chatbot Messenger Webhook is running',
        'page_type': 'Business Manager' if config.use_business_manager else 'Personal',
        'active_conversations': len(active_conversations),
        'timestamp': datetime.now().isoformat()
    }

@app.route('/health', methods=['GET'])
def health_check():
    """Enhanced health check for Business Manager monitoring"""
    health_status = {
        'status': 'healthy',
        'page_type': 'Business Manager' if config.use_business_manager else 'Personal',
        'active_conversations': len(active_conversations),
        'configuration': {
            'anthropic_configured': bool(config.anthropic_api_key),
            'criteria_file_exists': os.path.exists(config.criteria_file),
            'data_directory_exists': os.path.exists(config.data_directory)
        },
        'timestamp': datetime.now().isoformat()
    }
    
    if config.use_business_manager:
        health_status['configuration'].update({
            'business_manager_configured': bool(config.system_user_token and config.business_id and config.page_id),
            'page_token_available': bool(auth_handler and auth_handler.get_page_token())
        })
    else:
        health_status['configuration']['facebook_configured'] = bool(config.facebook_page_token and config.facebook_verify_token)
    
    return jsonify(health_status)

@app.route('/test/business-manager', methods=['GET'])
def test_business_manager():
    """Test Business Manager setup and permissions"""
    if not config.use_business_manager:
        return jsonify({
            'status': 'not_applicable',
            'message': 'Not configured for Business Manager'
        })
    
    if not auth_handler:
        return jsonify({
            'status': 'error',
            'message': 'Business Manager authentication handler not initialized'
        }), 500
    
    try:
        verification_results = auth_handler.verify_business_manager_setup()
        
        overall_status = 'success' if all([
            verification_results['system_user_token_valid'],
            verification_results['page_accessible'],
            verification_results['page_token_generated']
        ]) else 'failed'
        
        return jsonify({
            'status': overall_status,
            'verification_results': verification_results,
            'message': 'Business Manager verification completed'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error testing Business Manager: {str(e)}'
        }), 500

@app.route('/test/webhook-subscription', methods=['POST'])
def test_webhook_subscription():
    """Test webhook subscription for Business Manager pages"""
    if not config.use_business_manager:
        return jsonify({
            'status': 'not_applicable',
            'message': 'Webhook subscription test only applies to Business Manager pages'
        })
    
    if not auth_handler:
        return jsonify({
            'status': 'error',
            'message': 'Business Manager authentication handler not available'
        }), 500
    
    try:
        success = auth_handler.setup_webhook_subscription()
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Webhook subscription successful'
            })
        else:
            return jsonify({
                'status': 'failed',
                'message': 'Webhook subscription failed - check logs for details'
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error testing webhook subscription: {str(e)}'
        }), 500

def run_startup_checks():
    """Run comprehensive startup checks for both page types"""
    try:
        logger.info("Running startup configuration checks...")
        
        # Check critical configuration
        critical_issues = []
        
        if not config.anthropic_api_key:
            critical_issues.append("Missing ANTHROPIC_API_KEY")
        
        if config.use_business_manager:
            if not config.system_user_token:
                critical_issues.append("Missing SYSTEM_USER_TOKEN")
            if not config.business_id:
                critical_issues.append("Missing BUSINESS_ID")
            if not config.page_id:
                critical_issues.append("Missing PAGE_ID")
        else:
            if not config.facebook_page_token:
                critical_issues.append("Missing PAGE_ACCESS_TOKEN")
        
        if not config.facebook_verify_token:
            critical_issues.append("Missing MESSENGER_VERIFY_TOKEN")
        
        if critical_issues:
            logger.error(f"Critical configuration issues: {', '.join(critical_issues)}")
            return False
        
        # Test API connections based on page type
        if config.use_business_manager and auth_handler:
            logger.info("Testing Business Manager setup...")
            verification = auth_handler.verify_business_manager_setup()
            if verification['errors']:
                logger.warning(f"Business Manager verification issues: {verification['errors']}")
            else:
                logger.info("Business Manager setup verified successfully")
        else:
            logger.info("Testing personal page Facebook API...")
            try:
                url = "https://graph.facebook.com/v22.0/me"
                params = {"access_token": config.facebook_page_token}
                response = requests.get(url, params=params, timeout=5)
                
                if response.status_code == 200:
                    page_data = response.json()
                    logger.info(f"Facebook API connected successfully. Page: {page_data.get('name', 'Unknown')}")
                else:
                    logger.warning(f"Facebook API test failed: {response.text}")
            except Exception as e:
                logger.warning(f"Could not test Facebook API: {e}")
        
        # Ensure data directory exists
        config.ensure_directory_exists(config.data_directory)
        
        logger.info("All startup checks completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error during startup checks: {e}")
        return False

if __name__ == '__main__':
    # Run startup checks
    if not run_startup_checks():
        logger.error("Startup checks failed. Exiting.")
        sys.exit(1)
    
    # Start the development server
    port = config.server_port
    logger.info(f"Starting Messenger webhook server on port {port}")
    logger.info(f"Page type: {'Business Manager' if config.use_business_manager else 'Personal'}")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False
    )
