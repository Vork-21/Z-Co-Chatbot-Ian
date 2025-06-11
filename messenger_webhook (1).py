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

# Import the new modular components
from config_manager import config
from conversation_manager import ConversationManager

# Configure comprehensive logging with the centralized manager
logger = config.get_logger("MessengerWebhook")
logger.info("=== MessengerWebhook Application Starting ===")

# Initialize Flask application
app = Flask(__name__)

# Active conversation sessions
active_conversations = {}

class MessengerSession:
    """
    Manages individual conversation sessions with Messenger users.
    Streamlined implementation focusing on core conversation flow.
    """
    
    def __init__(self, sender_id: str):
        self.sender_id = sender_id
        self.conversation_manager = ConversationManager()
        self.conversation_active = True
        self.last_activity = time.time()
        self.handled_by_agent = False
        
        logger.info(f"New session created for sender {sender_id}")
    
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
            # Process message through conversation manager
            response_data = self.conversation_manager.analyze_response(message_text)
            
            # Handle various response types
            if 'error' in response_data:
                self._send_message(response_data['error'])
                return
            
            if 'help' in response_data:
                self._send_message(response_data['help'])
                return
            
            if 'back' in response_data:
                next_question, _ = self.conversation_manager.get_next_question()
                self._send_message(f"Let's go back to a previous question. {next_question}")
                return
            
            if not response_data.get('eligible', True):
                self._send_message(response_data['reason'])
                self._transition_to_agent("Case ineligible - needs human review")
                return
            
            if response_data.get('end_chat'):
                farewell_message = response_data.get('farewell_message', "Thank you for your time.")
                self._send_message(farewell_message)
                self.conversation_active = False
                return
            
            # Prepare response message
            sympathy_message = response_data.get('sympathy_message', '')
            next_question, is_control = self.conversation_manager.get_next_question()
            
            if is_control and self.conversation_manager.empty_response_count >= 3:
                self._send_message(next_question)
                return
            
            # Handle completion of conversation
            if self.conversation_manager.current_phase == 'complete':
                self._send_message(next_question)
                self._transition_to_agent("Case completed - ready for human consultation")
                return
            
            # Send next question with any sympathy message
            full_message = sympathy_message + (" " if sympathy_message else "") + next_question
            self._send_message(full_message)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self._send_message("I'm having trouble processing your message. Let me connect you with a live representative.")
            self._transition_to_agent("Error processing message")
    
    def _send_message(self, message_text: str, retry_count: int = 3) -> bool:
        """Send message to user via Facebook Messenger API with retry logic"""
        attempt = 0
        
        while attempt < retry_count:
            try:
                url = "https://graph.facebook.com/v22.0/me/messages"
                payload = {
                    "recipient": {"id": self.sender_id},
                    "message": {"text": message_text},
                    "messaging_type": "RESPONSE"
                }
                params = {"access_token": config.facebook_page_token}
                
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
                
                logger.error(f"Failed to send message: {response.text}")
                return False
                
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                attempt += 1
                
        return False
    
    def _transition_to_agent(self, reason: str) -> None:
        """Mark conversation for human agent handling"""
        self.handled_by_agent = True
        logger.info(f"Conversation {self.sender_id} transitioned to agent. Reason: {reason}")
        
        try:
            # Get case summary for logging
            case_summary = self.conversation_manager.get_case_summary()
            age = case_summary.get('age', 'Unknown')
            state = case_summary.get('state', 'Unknown')
            ranking = case_summary.get('ranking', 'normal')
            points = case_summary.get('points', 0)
            
            # Generate case reference ID
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            ref_id = f"{timestamp[-6:]}_{random_suffix}"
            
            # Log case details for manual agent review
            logger.info(f"Case transition details - Ref: #{ref_id}, Age: {age}, State: {state}, Ranking: {ranking} ({points} points), Reason: {reason}")
            
            # Notify user about agent handoff
            self._send_message(f"Thank you for providing your information. A team member will review your case (Ref: #{ref_id}) and continue this conversation shortly.")
            
        except Exception as e:
            logger.error(f"Error during agent transition: {e}")
            self._send_message("I'll connect you with a representative who can help you further. They'll respond shortly.")
    
    def send_welcome_message(self) -> None:
        """Send initial age question to begin conversation"""
        age_question = self.conversation_manager.get_next_question()[0]
        self._send_message(age_question)
        logger.info(f"Sent welcome message to {self.sender_id}: {age_question}")

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
    # Use underscores to match what Facebook actually sends
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
    # Add comprehensive logging at the very start
    logger.info("=== WEBHOOK POST REQUEST RECEIVED ===")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Raw data: {request.get_data()}")
    logger.info(f"Content-Type: {request.content_type}")
    logger.info(f"Content-Length: {request.content_length}")
    
    # Verify request signature
    signature = request.headers.get('X-Hub-Signature', '')
    logger.info(f"Signature header: {signature}")
    
    if not verify_facebook_signature(request.get_data(), signature):
        logger.warning("Invalid request signature")
        return 'Invalid signature', 403
    
    # Rest of your existing webhook code...
    
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
        'active_conversations': len(active_conversations),
        'timestamp': datetime.now().isoformat()
    }

@app.route('/health', methods=['GET'])
def health_check():
    """Detailed health check for monitoring"""
    return jsonify({
        'status': 'healthy',
        'active_conversations': len(active_conversations),
        'configuration': {
            'anthropic_configured': bool(config.anthropic_api_key),
            'facebook_configured': bool(config.facebook_page_token and config.facebook_verify_token),
            'criteria_file_exists': os.path.exists(config.criteria_file),
            'data_directory_exists': os.path.exists(config.data_directory)
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/test/configuration', methods=['GET'])
def test_configuration():
    """Test endpoint to verify all configuration is properly loaded"""
    tests = {
        'environment_loaded': config._env_loaded,
        'anthropic_api_key': bool(config.anthropic_api_key),
        'facebook_page_token': bool(config.facebook_page_token),
        'facebook_verify_token': bool(config.facebook_verify_token),
        'facebook_app_secret': bool(config.facebook_app_secret),
        'claude_model_valid': config.validate_claude_model_version(config.claude_model_version),
        'criteria_file_exists': os.path.exists(config.criteria_file),
        'data_directory_accessible': os.path.isdir(config.data_directory)
    }
    
    all_passed = all(tests.values())
    
    return jsonify({
        'status': 'passed' if all_passed else 'failed',
        'tests': tests,
        'config_summary': {
            'model_version': config.claude_model_version,
            'data_directory': config.data_directory,
            'criteria_file': config.criteria_file,
            'server_port': config.server_port
        }
    }), 200 if all_passed else 500

@app.route('/test/facebook-api', methods=['GET'])
def test_facebook_api():
    """Test Facebook Graph API connectivity"""
    try:
        url = "https://graph.facebook.com/v22.0/me"
        params = {"access_token": config.facebook_page_token}
        response = requests.get(url, params=params, timeout=config.api_timeout)
        
        if response.status_code == 200:
            page_data = response.json()
            return jsonify({
                'status': 'success',
                'page_id': page_data.get('id'),
                'page_name': page_data.get('name'),
                'message': 'Facebook API connection successful'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Facebook API error: {response.text}'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error testing Facebook API: {str(e)}'
        }), 500

@app.route('/test/conversation', methods=['POST'])
def test_conversation():
    """Test conversation flow with simulated messages"""
    try:
        data = request.json
        test_messages = data.get('messages', ['5 years old'])
        
        # Create test conversation manager
        conversation_manager = ConversationManager()
        results = []
        
        for message in test_messages:
            response_data = conversation_manager.analyze_response(message)
            next_question, is_control = conversation_manager.get_next_question()
            
            results.append({
                'input': message,
                'response_data': response_data,
                'next_question': next_question,
                'current_phase': conversation_manager.current_phase,
                'case_summary': conversation_manager.get_case_summary()
            })
        
        return jsonify({
            'status': 'success',
            'conversation_results': results
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error testing conversation: {str(e)}'
        }), 500

def run_startup_checks():
    """Run comprehensive startup checks"""
    try:
        logger.info("Running startup configuration checks...")
        
        # Check critical configuration
        critical_issues = []
        
        if not config.anthropic_api_key:
            critical_issues.append("Missing ANTHROPIC_API_KEY")
        
        if not config.facebook_page_token:
            critical_issues.append("Missing PAGE_ACCESS_TOKEN")
        
        if not config.facebook_verify_token:
            critical_issues.append("Missing MESSENGER_VERIFY_TOKEN")
        
        if critical_issues:
            logger.error(f"Critical configuration issues: {', '.join(critical_issues)}")
            return False
        
        # Test Facebook API connection
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
        
        # Test conversation components
        try:
            test_conversation = ConversationManager()
            logger.info("Conversation manager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize conversation manager: {e}")
            return False
        
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
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False  # Set to False for production stability
    )