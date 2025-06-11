import json
import re
import logging
from typing import Dict, Optional, Tuple, Any
from config_manager import config

class EligibilityChecker:
    """
    Handles all eligibility checking and criteria validation for CP cases.
    Maintains exact functionality from the original Chat_Deploy.py implementation.
    """
    
    def __init__(self, criteria_file_path: Optional[str] = None):
        self.logger = config.get_logger("EligibilityChecker")
        self.criteria_file = criteria_file_path or config.criteria_file
        self.legal_rules = self._load_criteria()
        
    def _load_criteria(self) -> Dict[str, Any]:
        """Load legal criteria from JSON file"""
        try:
            with open(self.criteria_file, 'r') as f:
                criteria = json.load(f)
                self.logger.info(f"Loaded legal criteria from {self.criteria_file}")
                return criteria
        except FileNotFoundError:
            self.logger.error(f"Criteria file not found: {self.criteria_file}")
            return {"stateSOL": {}, "globalExclusions": {"excludedStates": {"list": []}}}
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in criteria file: {e}")
            return {"stateSOL": {}, "globalExclusions": {"excludedStates": {"list": []}}}
        except Exception as e:
            self.logger.error(f"Error loading criteria file: {e}")
            return {"stateSOL": {}, "globalExclusions": {"excludedStates": {"list": []}}}
    
    def check_state_exclusion(self, state: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a state is in the excluded states list.
        Returns (is_excluded, reason) tuple.
        """
        if not state:
            return False, None
            
        excluded_states = self.legal_rules.get('globalExclusions', {}).get('excludedStates', {}).get('list', [])
        
        if state in excluded_states:
            reason = f"We apologize, but we are currently not accepting cases from {state}."
            self.logger.info(f"State {state} is excluded")
            return True, reason
            
        return False, None
    
    def parse_sol_age(self, sol_string: str) -> Optional[float]:
        """
        Convert SOL string to numerical age limit.
        Handles both "Nth birthday" and "N years" formats.
        Preserved from original SOLParser.parse_sol_age()
        """
        if not sol_string:
            return None
            
        # Handle "Nth birthday" format
        birthday_match = re.search(r'(\d+)(?:st|nd|rd|th)\s*birthday', sol_string)
        if birthday_match:
            return float(birthday_match.group(1))
            
        # Handle "N years" format
        years_match = re.search(r'(\d+)\s*years?', sol_string)
        if years_match:
            return float(years_match.group(1))
            
        # Handle just number
        num_match = re.search(r'(\d+)', sol_string)
        if num_match:
            return float(num_match.group(1))
            
        return None
    
    def is_within_sol(self, current_age: float, sol_string: str) -> bool:
        """
        Check if current age is within the SOL limit.
        For "Nth birthday" format, must be under N years old.
        For "N years" format, must be under N years old.
        Preserved from original SOLParser.is_within_sol()
        """
        sol_age = self.parse_sol_age(sol_string)
        if sol_age is None:
            return False
            
        # Always check if current age is less than SOL age
        return current_age < sol_age
    
    def check_age_eligibility(self, age: float, state: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Check if age meets eligibility criteria for given state.
        Preserved from original ConversationManager.check_age_eligibility()
        """
        if age is None:
            return False, "Unable to determine age eligibility without age information."
            
        # Basic age check (maximum age across all states)
        if age >= 21:
            return False, "We apologize, but based on your child's age, we cannot proceed with your case."
        
        # State-specific check if state is provided
        if state and state in self.legal_rules.get('stateSOL', {}):
            state_sol = self.legal_rules['stateSOL'][state].get('minorSOL')
            if state_sol and not self.is_within_sol(age, state_sol):
                return False, f"We apologize, but based on your child's age and {state}'s requirements, we cannot proceed with your case."
        
        return True, None
    
    def check_comprehensive_eligibility(self, age: Optional[float], state: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        Comprehensive eligibility check combining all criteria.
        Preserved from original ConversationManager.check_eligibility()
        """
        # Check both age and state if available
        if age is not None and state is not None:
            # First check excluded states list - this is a true disqualifier
            is_excluded, exclusion_reason = self.check_state_exclusion(state)
            if is_excluded:
                return False, exclusion_reason
            
            # Check age eligibility with state context - SOL is a true disqualifier
            is_eligible, age_reason = self.check_age_eligibility(age, state)
            if not is_eligible:
                return False, age_reason
        
        # Check age alone if that's all we have - SOL is a true disqualifier
        elif age is not None:
            is_eligible, age_reason = self.check_age_eligibility(age)
            if not is_eligible:
                return False, age_reason
        
        return True, None
    
    def get_state_info(self, state: str) -> Optional[Dict[str, Any]]:
        """Get SOL and other information for a specific state"""
        return self.legal_rules.get('stateSOL', {}).get(state)
    
    def validate_age_range(self, age: float) -> bool:
        """
        Validate if age is within reasonable range for CP cases.
        Preserved from original AgeParser.is_age_valid()
        """
        return 0 <= age <= 25
    
    def normalize_age(self, age: Optional[float]) -> Optional[float]:
        """
        Normalize age value to handle edge cases.
        Preserved from original AgeParser.normalize_age()
        """
        if age is None:
            return None
            
        # Round to 1 decimal place for consistency
        age = round(age, 1)
        
        # Ensure within valid range
        if age < 0:
            return 0.0
        if age > 25:
            return 25.0
            
        return age
    
    def get_excluded_states(self) -> list:
        """Get list of excluded states"""
        return self.legal_rules.get('globalExclusions', {}).get('excludedStates', {}).get('list', [])
    
    def get_all_states_with_sol(self) -> Dict[str, str]:
        """Get all states with their SOL information"""
        states_sol = {}
        state_data = self.legal_rules.get('stateSOL', {})
        
        for state, info in state_data.items():
            sol = info.get('minorSOL', 'Unknown')
            states_sol[state] = sol
            
        return states_sol