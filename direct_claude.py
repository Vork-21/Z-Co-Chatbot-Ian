"""
Standalone Claude API client implementation that bypasses Python's module system.
This implementation uses direct HTTP requests without depending on the Anthropic SDK.
"""
import requests
import json
import logging
import time
from typing import Optional, Dict, Any, List

# Configure logging
logger = logging.getLogger("DirectClaude")

class DirectClaudeClient:
    """Pure HTTP-based implementation of Claude API client"""
    
    def __init__(self, api_key: str):
        """Initialize with API key only"""
        self.api_key = api_key
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.model = "claude-3-5-sonnet-20241022"
        self.max_retries = 3
        logger.info("Direct Claude client initialized successfully")
    
    def query(self, system_prompt: str, user_input: str, max_tokens: int = 150, 
              temperature: float = 0.1, timeout: int = 30) -> str:
        """
        Send a request directly to the Claude API with retry logic
        
        Args:
            system_prompt: The system prompt to send to Claude
            user_input: The user message to send to Claude
            max_tokens: Maximum tokens in the response
            temperature: Temperature parameter (0-1)
            timeout: Request timeout in seconds
            
        Returns:
            String containing Claude's response or empty string on failure
        """
        headers = {
            "anthropic-version": "2023-06-01",
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_input}],
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        for attempt in range(self.max_retries):
            try:
                # Create a fresh session for each request to avoid any cached settings
                session = requests.Session()
                
                # Explicitly disable proxies
                session.proxies = {}
                
                # Make the request
                response = session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    content = data.get("content", [])
                    if content and len(content) > 0:
                        return content[0].get("text", "")
                    else:
                        logger.warning("Empty content in response")
                        return ""
                else:
                    logger.warning(f"API call failed (Attempt {attempt+1}/{self.max_retries}): "
                                  f"Status {response.status_code}, Response: {response.text}")
            except Exception as e:
                wait_time = (attempt + 1) * 2
                logger.warning(f"Request failed (Attempt {attempt+1}/{self.max_retries}): {e}. "
                              f"Retrying in {wait_time}s")
                time.sleep(wait_time)
                
        # All attempts failed
        logger.error(f"All {self.max_retries} attempts to query Claude API failed")
        return ""

# Convenience function to create client
def create_client(api_key: str) -> DirectClaudeClient:
    """Create and return a DirectClaudeClient instance"""
    return DirectClaudeClient(api_key)