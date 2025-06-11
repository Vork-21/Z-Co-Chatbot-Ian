import json
import re
import logging
import time
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
# Import standalone implementation instead of anthropic
from claude_standalone import get_client
from config_manager import config

class NLUProcessor:
    """
    Natural Language Understanding processor with Claude AI integration.
    Handles conversation analysis with robust fallback to pattern matching.
    Preserves all functionality from the original ClaudeNLU class.
    """
    
    def __init__(self):
        self.logger = config.get_logger("NLUProcessor")
        self.client = self._initialize_claude_client()
        self.model = config.claude_model_version
        
        # Text to number mapping for age parsing
        self.text_to_num = {
            'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 
            'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
            'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 
            'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 
            'eighteen': 18, 'nineteen': 19, 'twenty': 20, 'thirty': 30, 
            'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70, 
            'eighty': 80, 'ninety': 90
        }
        
        # State abbreviation mappings for fallback parsing
        self.state_abbreviations = {
            'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
            'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
            'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
            'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
            'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
            'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
            'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
            'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
            'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
            'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
            'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
            'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
            'WI': 'Wisconsin', 'WY': 'Wyoming', 'DC': 'District of Columbia'
        }
    
    def _initialize_claude_client(self) -> Optional[Any]:
        """Initialize Claude client using standalone implementation"""
        try:
            # Use the standalone implementation that bypasses proxy issues
            client = get_client()
            self.logger.info("Claude client initialized using standalone implementation")
            return client
        except Exception as e:
            self.logger.error(f"Failed to initialize Claude client: {e}")
            return None
    
    def _query_claude(self, system_prompt: str, user_input: str) -> str:
        """
        Query Claude with retry logic and error handling.
        Using the standalone client's ask method instead of Anthropic SDK.
        Returns empty string on failure to allow fallback to pattern matching.
        """
        if not self.client:
            self.logger.warning("Claude client not available, using fallback parsing")
            return ""
        
        # Limit input length to prevent token issues
        max_length = config.max_response_length
        if len(user_input) > max_length:
            self.logger.warning(f"Truncating input from {len(user_input)} to {max_length} chars")
            user_input = user_input[:max_length] + "..."
        
        for attempt in range(config.max_retries):
            try:
                # Use standalone client's ask method
                response = self.client.ask(
                    message=user_input,
                    system_prompt=system_prompt,
                    max_tokens=150
                )
                return response.strip()
                
            except Exception as e:
                wait_time = (attempt + 1) * 2
                self.logger.warning(f"Claude API attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s")
                if attempt < config.max_retries - 1:
                    time.sleep(wait_time)
        
        self.logger.error(f"Claude API failed after {config.max_retries} attempts, using fallback")
        return ""
    
    def interpret_age(self, user_input: str) -> Optional[float]:
        """
        Extract age from natural language input with Claude AI and regex fallback.
        Preserves exact functionality from original ClaudeNLU.interpret_age()
        """
        if not user_input or len(user_input.strip()) == 0:
            return None
        
        # Try Claude first
        claude_result = self._query_claude(
            """Extract the child's age in years from this text. Respond with ONLY a number.
            If the age includes partial years (like "5 and a half"), convert to a decimal (5.5).
            If the age is given in months (like "18 months"), convert to years (1.5).
            If you can't determine the age, respond with "unknown".""",
            user_input
        )
        
        if claude_result:
            try:
                age = float(claude_result.strip().replace(',', '.'))
                return age
            except ValueError:
                pass
        
        # Fallback to pattern matching
        return self._parse_age_patterns(user_input)
    
    def _parse_age_patterns(self, user_input: str) -> Optional[float]:
        """
        Parse age using regex patterns as fallback.
        Enhanced version of original AgeParser logic.
        """
        age_input = user_input.lower().strip()
        
        # Check for months format first
        months_match = re.search(r'(\d+)\s*(?:months?|mos?)\s*old', age_input)
        if months_match:
            try:
                months = float(months_match.group(1))
                return round(months / 12.0, 1)
            except ValueError:
                pass
        
        # Handle "almost X" pattern - FIXED to return X-0.1
        almost_match = re.search(r'almost\s*(\d+)', age_input)
        if almost_match:
            try:
                age = float(almost_match.group(1))
                return age - 0.1  # Return 5.9 for "almost 6"
            except ValueError:
                pass
        
        # Age patterns from original implementation
        age_patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:year|yr|y)s?\s*old',
            r'(\d+(?:\.\d+)?)\s*(?:year|yr|y)s?',
            r'(?:is|turned|age)\s*(\d+(?:\.\d+)?)',
            r'^(\d+(?:\.\d+)?)$',
            r'(\d+)\s*(?:and a half|and 1/2)',
            r'(\d+)\s*(?:and three quarters|and 3/4)',
            r'(\d+)\s*(?:and a quarter|and 1/4)',
            r'just turned\s*(\d+)',
            r'about to turn\s*(\d+)',
        ]
        
        # Check fractional expressions
        fraction_modifiers = {
            'and a half': 0.5, 'and 1/2': 0.5,
            'and a quarter': 0.25, 'and 1/4': 0.25,
            'and three quarters': 0.75, 'and 3/4': 0.75
        }
        
        for pattern, modifier in fraction_modifiers.items():
            if pattern in age_input:
                base_match = re.search(r'(\d+)\s*' + re.escape(pattern), age_input)
                if base_match:
                    try:
                        return float(base_match.group(1)) + modifier
                    except ValueError:
                        continue
        
        # Try each regular pattern
        for pattern in age_patterns:
            match = re.search(pattern, age_input)
            if match:
                age_str = match.group(1)
                
                # Handle textual numbers
                if age_str in self.text_to_num:
                    return float(self.text_to_num[age_str])
                
                try:
                    age = float(age_str)
                    # Validate reasonable age range
                    if 0 <= age <= 25:
                        return age
                except ValueError:
                    continue
        
        return None
    
    def interpret_pregnancy_details(self, user_input: str) -> Dict[str, Any]:
        """
        Extract gestational age and delivery difficulty with Claude AI and regex fallback.
        Preserves exact functionality from original ClaudeNLU.interpret_pregnancy_details()
        """
        if not user_input:
            return {"weeks": None, "difficult_delivery": False}
        
        # Try Claude first
        claude_result = self._query_claude(
            """Extract two pieces of information from this text about a child's birth:
            1. The number of weeks pregnant (gestational age) when the child was born
            2. Whether there was a difficult delivery
            
            Respond with ONLY a JSON object with two keys:
            - "weeks": number (or null if not mentioned)
            - "difficult_delivery": boolean (true if any indication of difficult/complicated/not easy delivery)
            
            Example response: {"weeks": 34, "difficult_delivery": true}""",
            user_input
        )
        
        if claude_result:
            try:
                return json.loads(claude_result.strip())
            except json.JSONDecodeError:
                pass
        
        # Fallback to pattern matching
        return self._parse_pregnancy_patterns(user_input)
    
    def _parse_pregnancy_patterns(self, user_input: str) -> Dict[str, Any]:
        """Parse pregnancy details using regex patterns as fallback"""
        text_lower = user_input.lower()
        
        # Parse weeks
        weeks = None
        weeks_patterns = [
            r'(\d+)\s*(?:weeks|week|wks|wk)',
            r'(\d+)\s*w\b'
        ]
        
        for pattern in weeks_patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    weeks = int(match.group(1))
                    break
                except ValueError:
                    pass
        
        # FIXED: Add explicit check for full term expressions
        if weeks is None and re.search(r'(?:full|term|full term|full-term)\b', text_lower):
            weeks = 40  # Full term is defined as 40 weeks
        
        # Check for difficult delivery indicators
        difficult_indicators = [
            'difficult', 'not easy', 'hard', 'complications', 'emergency', 
            'c-section', 'csection', 'c section', 'cesarean', 'forceps', 
            'vacuum', 'distress', 'oxygen', 'resuscitate', 'nicu', 
            'intensive care', 'problem', 'complication', 'issue',
            'prolonged', 'stuck', 'trauma', 'injury', 'monitor', 'fetal',
            'induced', 'induction', 'premature', 'preemie', 'breech'
        ]
        
        difficult_delivery = any(indicator in text_lower for indicator in difficult_indicators)
        
        return {"weeks": weeks, "difficult_delivery": difficult_delivery}
    
    def interpret_yes_no(self, user_input: str, context: str = "") -> bool:
        """
        Determine if response is affirmative or negative with Claude AI and pattern fallback.
        Preserves exact functionality from original ClaudeNLU.interpret_yes_no()
        """
        if not user_input:
            return False
        
        # Check if this is a milestones question and we need special handling
        if "developmental milestones" in context.lower():
            # Check for normal development indicators - these override yes/no
            normal_indicators = [
                'no delays', 'meeting milestones', 'on track', 'normal development',
                'no major delays', 'everything seems normal', 'developing normally',
                'no issues', 'no problems', 'no concerns', 'normal', 'typical'
            ]
            
            if any(indicator in user_input.lower() for indicator in normal_indicators):
                return False
        
        # Quick check for simple responses
        user_input_lower = user_input.lower().strip()
        if user_input_lower in ['yes', 'yeah', 'yep', 'yup', 'sure', 'definitely', 'absolutely', 'correct']:
            return True
        if user_input_lower in ['no', 'nope', 'not', 'never', 'negative']:
            return False
        
        # Try Claude for complex responses
        claude_result = self._query_claude(
            f"""Determine if this response is affirmative (yes) or negative (no).
            Context about the question: {context}
            
            Respond with ONLY "yes" or "no".
            When in doubt and the response indicates any affirmative element, respond with "yes".""",
            user_input
        )
        
        if claude_result:
            return claude_result.strip().lower() == "yes"
        
        # Fallback to pattern matching
        return self._parse_yes_no_patterns(user_input, context)
    
    def _parse_yes_no_patterns(self, user_input: str, context: str = "") -> bool:
        """Parse yes/no responses using patterns as fallback"""
        message_lower = user_input.lower().strip()
        
        # FIXED: Check for special case patterns based on context
        if "cooling" in context.lower() or "hie therapy" in context.lower():
            cooling_indicators = ['cooling', 'hypothermia', 'hie therapy', 'head cool', 'cooling blanket']
            cooling_negative = ['no cooling', 'didn\'t receive cooling', 'without cooling', 'no hypothermia']
            
            if any(indicator in message_lower for indicator in cooling_indicators):
                if any(neg in message_lower for neg in cooling_negative):
                    return False
                else:
                    return True
                    
        if "brain scan" in context.lower() or "mri" in context.lower():
            scan_indicators = ['mri', 'brain scan', 'head scan', 'cat scan', 'ct scan', 'ultrasound']
            scan_negative = ['no scan', 'didn\'t have scan', 'no mri', 'without scan', 'no scans']
            
            if any(indicator in message_lower for indicator in scan_indicators):
                if any(neg in message_lower for neg in scan_negative):
                    return False
                else:
                    return True
        
        # Positive indicators
        positive_phrases = [
            'i do', 'we did', 'that is right', 'that is correct', 
            'that\'s right', 'that\'s correct', 'had to', 'did have',
            'we had', 'they did', 'doctor', 'received', 'cooling', 'blanket',
            'mri', 'brain scan', 'scan', 'behind', 'delayed', 'delay', 'missing',
            'not meeting', 'therapy', 'treatment', 'cool', 'attorney', 'spoke', 'spoken'
        ]
        
        if any(phrase in message_lower for phrase in positive_phrases):
            return True
        
        # Check for uncertainty phrases
        uncertainty_phrases = ['i think', 'maybe', 'possibly', 'probably', 'might have', 'could have', 'not sure']
        negative_indicators = ['no', 'not', 'never', 'don\'t', 'didn\'t', 'doesn\'t', 'don\'t think']
        
        if any(phrase in message_lower for phrase in uncertainty_phrases):
            return not any(neg in message_lower for neg in negative_indicators)
        
        return False
    
    def interpret_duration(self, user_input: str) -> int:
        """
        Extract duration in days from natural language with Claude AI and regex fallback.
        Preserves exact functionality from original ClaudeNLU.interpret_duration()
        """
        if not user_input:
            return 0
        
        # Try Claude first
        claude_result = self._query_claude(
            """Extract the duration mentioned in this text and convert it to total days.
            Respond with ONLY the number of days as an integer.
            
            For example:
            - "2 weeks" → 14
            - "3 days" → 3
            - "a week and a half" → 10
            - "2 months and 5 days" → 65
            - "a couple of days" → 2
            - "a few weeks" → 21
            
            If you can't determine a specific duration, respond with "0".""",
            user_input
        )
        
        if claude_result:
            try:
                return int(claude_result.strip())
            except ValueError:
                pass
        
        # Fallback to pattern matching
        return self._parse_duration_patterns(user_input)
    
    def _parse_duration_patterns(self, user_input: str) -> int:
        """Parse duration using regex patterns as fallback"""
        user_input_lower = user_input.lower()
        total_days = 0
        
        # FIXED: Add specific pattern for "spent X [unit] in NICU" format
        nicu_duration_pattern = r'(?:spent|stayed|was in)(?:\s+\w+)?\s+(\d+)\s+(days?|weeks?|months?)\s+(?:in|at)\s+(?:the\s+)?(?:nicu|intensive care)'
        nicu_duration_match = re.search(nicu_duration_pattern, user_input_lower)
        if nicu_duration_match:
            duration_num = float(nicu_duration_match.group(1))
            duration_unit = nicu_duration_match.group(2)
            
            if 'week' in duration_unit:
                return int(duration_num * 7)  # Convert weeks to days
            elif 'month' in duration_unit:
                return int(duration_num * 30)  # Convert months to days
            else:  # days
                return int(duration_num)
        
        # Parse months, weeks, days with more precise patterns
        month_match = re.search(r'(\d+)\s*(?:months?|mos?)', user_input_lower)
        if month_match:
            try:
                months = int(month_match.group(1))
                total_days += months * 30  # Approximate
            except (ValueError, TypeError):
                pass
        
        week_match = re.search(r'(\d+)\s*(?:weeks?|wks?)', user_input_lower)
        if week_match:
            try:
                weeks = int(week_match.group(1))
                total_days += weeks * 7
            except (ValueError, TypeError):
                pass
        
        day_match = re.search(r'(\d+)\s*(?:days?|d)\b', user_input_lower)
        if day_match:
            try:
                days = int(day_match.group(1))
                total_days += days
            except (ValueError, TypeError):
                pass
        
        # If we found explicit time units, return that total
        if total_days > 0:
            return total_days
        
        # Check for standalone numbers (assume days if no unit specified)
        number_match = re.search(r'\b(\d+)\b', user_input_lower)
        if number_match:
            try:
                number = int(number_match.group(1))
                # If the number is reasonable for days, use it
                if 1 <= number <= 365:
                    return number
            except (ValueError, TypeError):
                pass
        
        # Common phrases with more specific checks
        if re.search(r'\bcouple\s+(?:of\s+)?days?\b', user_input_lower):
            total_days += 2
        elif re.search(r'\bfew\s+(?:of\s+)?days?\b', user_input_lower):
            total_days += 3
        elif re.search(r'\bcouple\s+(?:of\s+)?weeks?\b', user_input_lower):
            total_days += 14
        elif re.search(r'\bfew\s+(?:of\s+)?weeks?\b', user_input_lower):
            total_days += 21
        elif re.search(r'\babout\s+a\s+week\b', user_input_lower):
            total_days += 7
        elif re.search(r'\bweek\s+and\s+(?:a\s+)?half\b', user_input_lower):
            total_days += 10
        elif re.search(r'\bcouple\s+(?:of\s+)?months?\b', user_input_lower):
            total_days += 60
        elif re.search(r'\bfew\s+(?:of\s+)?months?\b', user_input_lower):
            total_days += 90
        
        return total_days
    
    def interpret_state(self, user_input: str) -> Optional[str]:
        """
        Extract U.S. state from natural language with Claude AI and regex fallback.
        Preserves exact functionality from original ClaudeNLU.interpret_state()
        """
        if not user_input:
            return None
        
        # Try Claude first
        claude_result = self._query_claude(
            """Extract the U.S. state mentioned in this text.
            Respond with ONLY the full state name with proper capitalization.
            Convert state abbreviations to full names (e.g., "NY" → "New York").
            
            If you can't determine a specific state, respond with "unknown".""",
            user_input
        )
        
        if claude_result and claude_result.lower() != "unknown":
            return claude_result.strip()
        
        # Fallback to pattern matching
        return self._parse_state_patterns(user_input)
    
    def _parse_state_patterns(self, user_input: str) -> Optional[str]:
        """Parse state using regex patterns as fallback"""
        # Check for state abbreviations
        for abbrev, full_name in self.state_abbreviations.items():
            pattern = r'\b' + abbrev + r'\b'
            if re.search(pattern, user_input):
                return full_name
        
        # Check for full state names
        state_names = list(self.state_abbreviations.values())
        for state in state_names:
            pattern = r'\b' + re.escape(state) + r'\b'
            if re.search(pattern, user_input, re.IGNORECASE):
                return state
        
        return None