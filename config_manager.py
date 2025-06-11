import os
import sys
import logging
import re
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

class ConfigurationManager:
    """
    Centralized configuration management for the CP Chatbot system.
    Handles environment variables, logging setup, and application settings.
    """
    
    def __init__(self):
        self._load_environment()
        self._clear_proxy_settings()
        self._setup_logging()
        self._validate_configuration()
        
    def _load_environment(self):
        """Load environment variables from .env file"""
        try:
            load_dotenv()
            self._env_loaded = True
        except Exception as e:
            print(f"Warning: Could not load .env file: {e}")
            self._env_loaded = False
    
    def _clear_proxy_settings(self):
        """
        Clear proxy environment variables that interfere with API calls.
        This addresses the primary cause of Anthropic API failures.
        """
        proxy_vars = [
            'HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
            'NO_PROXY', 'no_proxy'
        ]
        
        for var in proxy_vars:
            if var in os.environ:
                del os.environ[var]
                
        # Ensure requests library uses the system certificates
        if not os.getenv('REQUESTS_CA_BUNDLE'):
            ca_bundle_path = '/etc/ssl/certs/ca-certificates.crt'
            if os.path.exists(ca_bundle_path):
                os.environ['REQUESTS_CA_BUNDLE'] = ca_bundle_path
    
    def _setup_logging(self):
        """Configure centralized logging for all application components"""
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Configure log formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # File handler with rotation
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'chatbot.log'),
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'  # Ensure UTF-8 encoding for file logs
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)
        
        # Console handler for development with encoding handling
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        # Create application-specific logger
        self.logger = logging.getLogger("CPChatbot")
        self.logger.info("Configuration manager initialized successfully")
    
    def _validate_configuration(self):
        """Validate that all required configuration is present"""
        required_vars = {
            'ANTHROPIC_API_KEY': 'Anthropic API key for Claude integration',
            'PAGE_ACCESS_TOKEN': 'Facebook Page Access Token',
            'MESSENGER_VERIFY_TOKEN': 'Facebook webhook verification token',
            'APP_SECRET': 'Facebook App Secret'
        }
        
        missing_vars = []
        for var, description in required_vars.items():
            if not self.get(var):
                missing_vars.append(f"{var} ({description})")
        
        if missing_vars:
            error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
            self.logger.error(error_msg)
            raise EnvironmentError(error_msg)
        
        self.logger.info("All required configuration variables are present")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get environment variable with optional default value"""
        return os.getenv(key, default)
    
    def get_int(self, key: str, default: int = 0) -> int:
        """Get environment variable as integer"""
        try:
            return int(self.get(key, default))
        except (ValueError, TypeError):
            return default
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get environment variable as boolean"""
        value = self.get(key, '').lower()
        return value in ('true', '1', 'yes', 'on')
    
    # Application-specific configuration properties
    @property
    def anthropic_api_key(self) -> str:
        """Anthropic API key for Claude integration"""
        return self.get('ANTHROPIC_API_KEY')
    
    @property
    def claude_model_version(self) -> str:
        """Claude model version to use"""
        return self.get('MODEL_VERSION', 'claude-3-5-sonnet-20241022')
    
    @property
    def facebook_page_token(self) -> str:
        """Facebook Page Access Token"""
        return self.get('PAGE_ACCESS_TOKEN')
    
    @property
    def facebook_verify_token(self) -> str:
        """Facebook webhook verification token"""
        return self.get('MESSENGER_VERIFY_TOKEN')
    
    @property
    def facebook_app_secret(self) -> str:
        """Facebook App Secret for webhook signature verification"""
        return self.get('APP_SECRET')
    
    @property
    def server_port(self) -> int:
        """Server port for local development"""
        return self.get_int('PORT', 5000)
    
    @property
    def data_directory(self) -> str:
        """Directory for case data storage"""
        return self.get('DATA_DIRECTORY', './case_data')
    
    @property
    def criteria_file(self) -> str:
        """Path to criteria.json file"""
        return self.get('CRITERIA_FILE', './criteria.json')
    
    @property
    def max_response_length(self) -> int:
        """Maximum length for user responses"""
        return self.get_int('MAX_RESPONSE_LENGTH', 5000)
    
    @property
    def api_timeout(self) -> int:
        """Timeout for API calls in seconds"""
        return self.get_int('API_TIMEOUT', 30)
    
    @property
    def max_retries(self) -> int:
        """Maximum number of API call retries"""
        return self.get_int('MAX_RETRIES', 3)
    
    def validate_claude_model_version(self, version: str) -> bool:
        """Validate Claude model version format"""
        pattern = r'claude-\d+(-\d+)?-[a-zA-Z]+-\d{8}'
        return bool(re.match(pattern, version))
    
    def ensure_directory_exists(self, directory: str):
        """Ensure a directory exists, creating it if necessary"""
        os.makedirs(directory, exist_ok=True)
        self.logger.info(f"Ensured directory exists: {directory}")
    
    def get_logger(self, name: str) -> logging.Logger:
        """Get a named logger instance"""
        return logging.getLogger(name)

# Global configuration instance
config = ConfigurationManager()