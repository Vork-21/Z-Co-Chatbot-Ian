import requests
import logging
import time
from typing import Optional, Dict, Any
from config_manager import config

class BusinessManagerAuth:
    """
    Handles Business Manager authentication and page token management.
    Uses Graph API v22.0 for all requests.
    """
    
    def __init__(self):
        self.logger = config.get_logger("BusinessManagerAuth")
        self.system_user_token = config.system_user_token
        self.business_id = config.business_id
        self.page_id = config.page_id
        self.page_access_token = None
        self.token_expires_at = None
        
        if config.use_business_manager:
            self._initialize_page_token()
    
    def _initialize_page_token(self):
        """Initialize page access token from system user token"""
        try:
            self.page_access_token = self._get_page_access_token()
            if self.page_access_token:
                config.set_generated_page_token(self.page_access_token)
                self.logger.info("Business Manager page token initialized successfully")
            else:
                raise Exception("Failed to generate page access token")
        except Exception as e:
            self.logger.error(f"Failed to initialize Business Manager authentication: {e}")
            raise
    
    def _get_page_access_token(self) -> Optional[str]:
        """Generate page access token using system user token with Graph API v22.0"""
        try:
            # Method 1: Direct page token request
            url = f"https://graph.facebook.com/v22.0/{self.page_id}"
            params = {
                'fields': 'access_token',
                'access_token': self.system_user_token
            }
            
            response = requests.get(url, params=params, timeout=config.api_timeout)
            
            if response.status_code == 200:
                data = response.json()
                token = data.get('access_token')
                if token:
                    self.logger.info("Successfully generated page token using direct method")
                    return token
            
            # Method 2: Fallback to accounts endpoint
            self.logger.info("Direct method failed, trying accounts endpoint")
            return self._get_token_via_accounts_endpoint()
            
        except Exception as e:
            self.logger.error(f"Error generating page access token: {e}")
            return None
    
    def _get_token_via_accounts_endpoint(self) -> Optional[str]:
        """Fallback method using /me/accounts endpoint with Graph API v22.0"""
        try:
            url = "https://graph.facebook.com/v22.0/me/accounts"
            params = {'access_token': self.system_user_token}
            
            response = requests.get(url, params=params, timeout=config.api_timeout)
            
            if response.status_code == 200:
                data = response.json()
                for page in data.get('data', []):
                    if page.get('id') == self.page_id:
                        token = page.get('access_token')
                        if token:
                            self.logger.info("Successfully generated page token using accounts endpoint")
                            return token
            
            self.logger.error(f"Accounts endpoint failed: {response.text}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error with accounts endpoint: {e}")
            return None
    
    def get_page_token(self) -> str:
        """Get current page access token, refreshing if necessary"""
        if not self.page_access_token:
            self._initialize_page_token()
        
        return self.page_access_token or ""
    
    def verify_business_manager_setup(self) -> Dict[str, Any]:
        """Verify Business Manager setup and permissions using Graph API v22.0"""
        verification_results = {
            'system_user_token_valid': False,
            'page_accessible': False,
            'page_token_generated': False,
            'webhook_subscription_possible': False,
            'errors': []
        }
        
        try:
            # Test 1: Verify system user token
            url = "https://graph.facebook.com/v22.0/me"
            params = {'access_token': self.system_user_token}
            response = requests.get(url, params=params, timeout=config.api_timeout)
            
            if response.status_code == 200:
                verification_results['system_user_token_valid'] = True
                user_data = response.json()
                self.logger.info(f"System user verified: {user_data.get('name', 'Unknown')}")
            else:
                verification_results['errors'].append(f"System user token invalid: {response.text}")
            
            # Test 2: Check page accessibility
            url = f"https://graph.facebook.com/v22.0/{self.page_id}"
            params = {
                'fields': 'id,name,category',
                'access_token': self.system_user_token
            }
            response = requests.get(url, params=params, timeout=config.api_timeout)
            
            if response.status_code == 200:
                verification_results['page_accessible'] = True
                page_data = response.json()
                self.logger.info(f"Page accessible: {page_data.get('name', 'Unknown')}")
            else:
                verification_results['errors'].append(f"Page not accessible: {response.text}")
            
            # Test 3: Generate page token
            page_token = self._get_page_access_token()
            if page_token:
                verification_results['page_token_generated'] = True
                self.logger.info("Page token generation successful")
                
                # Test 4: Check webhook subscription capability
                webhook_url = f"https://graph.facebook.com/v22.0/{self.page_id}/subscribed_apps"
                params = {'access_token': page_token}
                response = requests.get(webhook_url, params=params, timeout=config.api_timeout)
                
                if response.status_code == 200:
                    verification_results['webhook_subscription_possible'] = True
                    self.logger.info("Webhook subscription capability verified")
                else:
                    verification_results['errors'].append(f"Webhook subscription failed: {response.text}")
            else:
                verification_results['errors'].append("Failed to generate page access token")
            
        except Exception as e:
            verification_results['errors'].append(f"Verification error: {str(e)}")
            self.logger.error(f"Business Manager verification failed: {e}")
        
        return verification_results
    
    def setup_webhook_subscription(self, webhook_url: str = None) -> bool:
        """Subscribe the Business Manager page to webhook events using Graph API v22.0"""
        try:
            page_token = self.get_page_token()
            if not page_token:
                self.logger.error("No page token available for webhook subscription")
                return False
            
            url = f"https://graph.facebook.com/v22.0/{self.page_id}/subscribed_apps"
            data = {
                'subscribed_fields': 'messages,messaging_postbacks,message_deliveries',
                'access_token': page_token
            }
            
            response = requests.post(url, data=data, timeout=config.api_timeout)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    self.logger.info("Webhook subscription successful")
                    return True
                else:
                    self.logger.error(f"Webhook subscription failed: {result}")
                    return False
            else:
                self.logger.error(f"Webhook subscription request failed: {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error setting up webhook subscription: {e}")
            return False
