#!/usr/bin/env python3
"""
Completely standalone implementation of Claude API access
that uses direct HTTP requests without any dependency on Anthropic SDK.
Enhanced with detailed response logging.
"""
import requests
import json
import logging
import os
import sys
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ClaudeStandalone")

class StandaloneClaudeClient:
    """Completely independent Claude API client implementation"""
    
    def __init__(self, api_key):
        """Initialize with API key only"""
        self.api_key = api_key
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.model = "claude-3-5-sonnet-20241022"
        logger.info("Standalone Claude client initialized")
    
    def ask(self, message, system_prompt="", max_tokens=500):
        """Send a message to Claude API and get the response"""
        headers = {
            "anthropic-version": "2023-06-01",
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Create payload
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": message}],
            "max_tokens": max_tokens
        }
        
        # Add system prompt if provided
        if system_prompt:
            payload["system"] = system_prompt
        
        # Log the request details
        request_id = f"req_{int(time.time())}_{hash(message) % 10000:04d}"
        truncated_message = message[:100] + "..." if len(message) > 100 else message
        logger.info(f"[{request_id}] Request: {truncated_message}")
        
        if system_prompt:
            truncated_system = system_prompt[:100] + "..." if len(system_prompt) > 100 else system_prompt
            logger.info(f"[{request_id}] System: {truncated_system}")
        
        logger.info(f"[{request_id}] Sending request to Claude API")
        
        # Create new session without proxy configuration
        session = requests.Session()
        session.proxies = {}  # Explicitly disable proxies
        
        try:
            # Make request
            start_time = time.time()
            response = session.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            request_time = time.time() - start_time
            
            # Process response
            if response.status_code == 200:
                data = response.json()
                text = data.get("content", [{}])[0].get("text", "")
                
                # Log complete API response for debugging
                logger.info(f"[{request_id}] API response received in {request_time:.2f}s")
                logger.info(f"[{request_id}] Response status: {response.status_code}")
                logger.info(f"[{request_id}] Response content type: {response.headers.get('Content-Type', 'unknown')}")
                logger.info(f"[{request_id}] Response length: {len(response.text)} bytes")
                
                # Log the actual response text content
                truncated_text = text[:200] + "..." if len(text) > 200 else text
                logger.info(f"[{request_id}] Response text ({len(text)} chars): {repr(truncated_text)}")
                
                # Log any API usage information
                if "x-usage" in response.headers:
                    logger.info(f"[{request_id}] API usage: {response.headers['x-usage']}")
                
                return text
            else:
                # Log error details
                logger.error(f"[{request_id}] API error: Status {response.status_code}")
                logger.error(f"[{request_id}] Error details: {response.text}")
                
                # Try to parse error JSON if available
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_type = error_data.get("error", {}).get("type", "unknown")
                        error_message = error_data.get("error", {}).get("message", "No error message")
                        logger.error(f"[{request_id}] Error type: {error_type}")
                        logger.error(f"[{request_id}] Error message: {error_message}")
                except Exception:
                    pass
                
                return f"Error: {response.status_code}"
        except Exception as e:
            logger.error(f"[{request_id}] Request failed: {e}")
            logger.error(f"[{request_id}] Exception type: {type(e).__name__}")
            return f"Error: {str(e)}"

# Create client factory function
def get_client():
    """Get a configured client instance"""
    from config_manager import config
    API_KEY = config.anthropic_api_key
    return StandaloneClaudeClient(api_key=API_KEY)

# For direct testing
if __name__ == "__main__":
    # Set up enhanced logging for direct testing
    file_handler = logging.FileHandler("claude_api_debug.log")
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    
    # Test with sample prompt
    client = get_client()
    response = client.ask("Hello, how are you?")
    print(f"Response: {response}")