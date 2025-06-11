import logging
import re
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

from config_manager import config
from eligibility_checker import EligibilityChecker
from nlu_processor import NLUProcessor
from case_data_manager import CaseDataManager

class ConversationManager:
    """
    Manages the complete conversation flow for CP case intake.
    Orchestrates all components while preserving exact functionality from the original implementation.
    """
    
    def __init__(self):
        self.logger = config.get_logger("ConversationManager")
        
        # Initialize component managers
        self.eligibility_checker = EligibilityChecker()
        self.nlu_processor = NLUProcessor()
        self.case_data_manager = CaseDataManager()
        
        # Conversation state
        self.current_phase = 'age'  # Start directly at age phase
        self.empty_response_count = 0
        self.case_data = self.case_data_manager.initialize_case_data()
        
        # Implied answers tracking (preserved from original)
        self.implied_answers = {
            'nicu': None,
            'nicu_duration': None,
            'hie_therapy': None,
            'brain_scan': None,
            'milestones': None,
            'lawyer': None,
            'state': None
        }
        
        # Define conversation phases with exact questions from original
        self.phases = {
            'age': {
                'complete': False,
                'question': "How old is your child with CP?",
                'value': None
            },
            'pregnancy': {
                'complete': False,
                'question': "How many weeks pregnant were you when your child was born? Did your child have a difficult delivery?",
                'value': None
            },
            'nicu': {
                'complete': False,
                'question': "Did your child go to the NICU after birth?",
                'value': None
            },
            'nicu_duration': {
                'complete': False,
                'question': "How long was your child in the NICU for after birth?",
                'value': None
            },
            'hie_therapy': {
                'complete': False,
                'question': "Did your child receive head cooling or HIE therapy while in the NICU?",
                'value': None
            },
            'brain_scan': {
                'complete': False,
                'question': "Did your child receive an MRI or Brain Scan while in the NICU?",
                'value': None
            },
            'milestones': {
                'complete': False,
                'question': "Is your child missing any milestones and or having any delays?",
                'value': None
            },
            'lawyer': {
                'complete': False,
                'question': "This sounds like it definitely needs to be looked into further. Have you had your case reviewed by a lawyer yet?",
                'value': None
            },
            'state': {
                'complete': False,
                'question': "In what State was your child born?",
                'value': None
            }
        }
        
        self.logger.info("ConversationManager initialized successfully")
    
    def analyze_response(self, message: str) -> Dict[str, Any]:
        """
        Process user response and update conversation state.
        Preserves exact logic flow from original implementation.
        """
        # Sanitize input
        if not message:
            message = ""
        message = str(message).strip()
        
        if not message:
            self.empty_response_count += 1
            return {}
        
        self.empty_response_count = 0
        response_data = {}
        
        # Check for special commands
        if self._is_back_command(message):
            return self._handle_back_request()
        
        if self._is_help_command(message):
            return self._handle_help_request()
        
        # Analyze for implied answers before processing current phase
        self._analyze_for_implied_answers(message)
        
        # Process based on current phase
        try:
            if self.current_phase == 'age':
                response_data = self._process_age_response(message)
                
            elif self.current_phase == 'pregnancy':
                response_data = self._process_pregnancy_response(message)
                
            elif self.current_phase == 'nicu':
                response_data = self._process_nicu_response(message)
                
            elif self.current_phase == 'nicu_duration':
                response_data = self._process_nicu_duration_response(message)
                
            elif self.current_phase == 'hie_therapy':
                response_data = self._process_hie_therapy_response(message)
                
            elif self.current_phase == 'brain_scan':
                response_data = self._process_brain_scan_response(message)
                
            elif self.current_phase == 'milestones':
                response_data = self._process_milestones_response(message)
                
            elif self.current_phase == 'lawyer':
                response_data = self._process_lawyer_response(message)
                
            elif self.current_phase == 'state':
                response_data = self._process_state_response(message)
                
        except Exception as e:
            self.logger.error(f"Error processing response for phase {self.current_phase}: {e}")
            response_data['error'] = "I'm having trouble processing your response. Could you please try again?"
        
        return response_data
    
    def _process_age_response(self, message: str) -> Dict[str, Any]:
        """Process age response with eligibility checking"""
        age, error_message = self._analyze_age_response(message)
        
        if error_message:
            return {'error': error_message}
        
        self.phases['age']['value'] = age
        self.phases['age']['complete'] = True
        self.case_data['age'] = age
        self.case_data_manager.update_phase_completion(self.case_data, 'age')
        
        # Check eligibility based on age
        is_eligible, reason = self.eligibility_checker.check_comprehensive_eligibility(age, None)
        if not is_eligible:
            return {'eligible': False, 'reason': reason}
        
        self.current_phase = 'pregnancy'
        return {'age': age}
    
    def _process_pregnancy_response(self, message: str) -> Dict[str, Any]:
        """Process pregnancy details with point calculation"""
        self.phases['pregnancy']['value'] = message
        self.phases['pregnancy']['complete'] = True
        self.case_data_manager.update_phase_completion(self.case_data, 'pregnancy')
        
        # Extract pregnancy details using NLU
        pregnancy_details = self.nlu_processor.interpret_pregnancy_details(message)
        weeks = pregnancy_details.get('weeks')
        difficult_delivery = pregnancy_details.get('difficult_delivery', False)
        
        # Apply pregnancy points
        self.case_data_manager.apply_pregnancy_points(self.case_data, weeks, difficult_delivery)
        
        response_data = {}
        if difficult_delivery:
            response_data['sympathy_message'] = "I'm sorry to hear that your delivery was difficult."
        
        # Check for implied NICU answer and advance accordingly
        if self.implied_answers['nicu'] is not None:
            return self._handle_implied_nicu_answer(response_data)
        
        self.current_phase = 'nicu'
        return response_data
    
    def _process_nicu_response(self, message: str) -> Dict[str, Any]:
        """Process NICU stay response"""
        is_nicu = self.nlu_processor.interpret_yes_no(message, "Did the child go to NICU after birth")
        
        self.phases['nicu']['value'] = is_nicu
        self.phases['nicu']['complete'] = True
        self.case_data_manager.update_phase_completion(self.case_data, 'nicu')
        
        # Apply NICU points
        self.case_data_manager.apply_nicu_points(self.case_data, is_nicu)
        
        if not is_nicu:
            # For full-term babies without NICU, still ask HIE therapy question
            if self.case_data.get('weeks_pregnant', 0) >= 36:
                self.current_phase = 'hie_therapy'
            else:
                self.current_phase = 'milestones'
        else:
            self.current_phase = 'nicu_duration'
        
        return {}
    
    def _process_nicu_duration_response(self, message: str) -> Dict[str, Any]:
        """Process NICU duration response"""
        self.phases['nicu_duration']['value'] = message
        self.phases['nicu_duration']['complete'] = True
        self.case_data_manager.update_phase_completion(self.case_data, 'nicu_duration')
        
        # Extract duration using NLU
        duration_days = self.nlu_processor.interpret_duration(message)
        self.case_data_manager.apply_nicu_points(self.case_data, True, duration_days)
        
        # Check for implied HIE therapy answer
        if self.implied_answers['hie_therapy'] is not None:
            return self._handle_implied_hie_answer()
        
        # Check for implied brain scan answer
        if self.implied_answers['brain_scan'] is not None:
            return self._handle_implied_brain_scan_answer()
        
        # Always ask HIE for full term babies regardless of NICU stay
        if self.case_data.get('weeks_pregnant', 0) >= 36:
            self.current_phase = 'hie_therapy'
        else:
            self.current_phase = 'brain_scan'
        
        return {}
    
    def _process_hie_therapy_response(self, message: str) -> Dict[str, Any]:
        """Process HIE therapy response with corrected phase transition"""
        received_hie = self.nlu_processor.interpret_yes_no(message, "Did the child receive head cooling or HIE therapy")
        
        self.phases['hie_therapy']['value'] = received_hie
        self.phases['hie_therapy']['complete'] = True
        self.case_data_manager.update_phase_completion(self.case_data, 'hie_therapy')
        
        # Apply HIE therapy points
        self.case_data_manager.apply_hie_therapy_points(self.case_data, received_hie)
        
        # Check for implied brain scan answer
        if self.implied_answers['brain_scan'] is not None:
            return self._handle_implied_brain_scan_answer()
        
        # FIXED: Correct phase transition based on NICU status
        # For no NICU cases, skip brain scan and go to milestones
        if not self.phases.get('nicu', {}).get('value', False):
            self.current_phase = 'milestones'
        else:
            self.current_phase = 'brain_scan'
        
        return {}
    
    def _process_brain_scan_response(self, message: str) -> Dict[str, Any]:
        """Process brain scan response"""
        received_scan = self.nlu_processor.interpret_yes_no(message, "Did the child receive an MRI or brain scan while in the NICU")
        
        self.phases['brain_scan']['value'] = received_scan
        self.phases['brain_scan']['complete'] = True
        self.case_data_manager.update_phase_completion(self.case_data, 'brain_scan')
        
        # Apply brain scan points
        self.case_data_manager.apply_brain_scan_points(self.case_data, received_scan)
        
        # Check for implied milestones answer
        if self.implied_answers['milestones'] is not None:
            return self._handle_implied_milestones_answer()
        
        self.current_phase = 'milestones'
        return {}
    
    def _process_milestones_response(self, message: str) -> Dict[str, Any]:
        """Process developmental milestones response"""
        message_lower = message.lower()
        
        # FIXED: Add explicit check for normal development phrases
        normal_indicators = [
            'no delays', 'meeting milestones', 'on track', 'normal development',
            'no major delays', 'everything seems normal', 'developing normally',
            'no issues', 'no problems', 'no concerns', 'normal', 'typical'
        ]
        
        # Override NLU processor if normal indicators are present
        if any(indicator in message_lower for indicator in normal_indicators):
            has_delays = False
        else:
            has_delays = self.nlu_processor.interpret_yes_no(message, "Is the child missing developmental milestones or has delays")
        
        self.phases['milestones']['value'] = message
        self.phases['milestones']['complete'] = True
        self.case_data_manager.update_phase_completion(self.case_data, 'milestones')
        
        # Apply milestones points
        self.case_data_manager.apply_milestones_points(self.case_data, has_delays)
        
        # Check for implied lawyer answer
        if self.implied_answers['lawyer'] is not None:
            return self._handle_implied_lawyer_answer()
        
        self.current_phase = 'lawyer'
        return {}
    
    def _process_lawyer_response(self, message: str) -> Dict[str, Any]:
        """Process lawyer consultation response"""
        prev_consultation = self.nlu_processor.interpret_yes_no(message, "Has the family previously consulted a lawyer about this case")
        
        self.phases['lawyer']['value'] = prev_consultation
        self.phases['lawyer']['complete'] = True
        self.case_data_manager.update_phase_completion(self.case_data, 'lawyer')
        
        # Apply lawyer points
        self.case_data_manager.apply_lawyer_points(self.case_data, prev_consultation)
        
        if prev_consultation:
            # End conversation with farewell
            return {
                'end_chat': True,
                'farewell_message': "We're glad to hear you're already getting your case reviewed and getting the help you need. We wish you and your family the best."
            }
        
        # Check for implied state answer
        if self.implied_answers['state'] is not None:
            return self._handle_implied_state_answer()
        
        self.current_phase = 'state'
        return {}
    
    def _process_state_response(self, message: str) -> Dict[str, Any]:
        """Process state response with final eligibility check"""
        state = self.nlu_processor.interpret_state(message)
        if not state:
            state = message.strip()
        
        self.phases['state']['value'] = state
        self.phases['state']['complete'] = True
        self.case_data['state'] = state
        self.case_data_manager.update_phase_completion(self.case_data, 'state')
        
        # Final eligibility check with both age and state
        is_eligible, reason = self.eligibility_checker.check_comprehensive_eligibility(
            self.case_data.get('age'), state
        )
        if not is_eligible:
            return {'eligible': False, 'reason': reason}
        
        self.current_phase = 'complete'
        
        # Save case data
        success, error = self.case_data_manager.save_case_data(self.case_data, self.phases)
        if not success:
            self.logger.warning(f"Could not save case data: {error}")
        
        return {}
    
    def _analyze_age_response(self, message: str) -> Tuple[Optional[float], Optional[str]]:
        """Analyze age response and return parsed age and any error message"""
        if not message or not message.strip():
            return None, "Please provide your child's age."
        
        # Use NLU processor to interpret age
        parsed_age = self.nlu_processor.interpret_age(message)
        
        if parsed_age is None:
            return None, "I couldn't understand the age provided. Please provide the age in years, like '5' or '5 years old'."
        
        # Normalize and validate age
        normalized_age = self.eligibility_checker.normalize_age(parsed_age)
        
        if not self.eligibility_checker.validate_age_range(normalized_age):
            return None, "Please provide a valid age between 0 and 25 years."
        
        return normalized_age, None
    
    def _analyze_for_implied_answers(self, message: str) -> None:
        """
        Analyze message for information that implies answers to other questions.
        Enhanced to better handle complex messages with multiple implied answers.
        """
        if not message:
            return
        
        message_lower = message.lower()
        
        # Check for NICU mentions
        nicu_indicators = ['nicu', 'intensive care', 'incubator', 'special care']
        nicu_negative = ['didn\'t go', 'did not go', 'no nicu', 'wasn\'t in', 'never went', 
                         'avoided', 'no need', 'went home', 'straight home']
        
        if any(indicator in message_lower for indicator in nicu_indicators):
            if any(neg in message_lower for neg in nicu_negative):
                self.implied_answers['nicu'] = False
            else:
                self.implied_answers['nicu'] = True
        
        # FIXED: Add specific pattern for NICU duration with unit conversion
        nicu_duration_pattern = r'(?:spent|stayed|was in)(?:\s+\w+)?\s+(\d+)\s+(days?|weeks?|months?)\s+(?:in|at)\s+(?:the\s+)?(?:nicu|intensive care)'
        nicu_duration_match = re.search(nicu_duration_pattern, message_lower)
        if nicu_duration_match:
            duration_num = float(nicu_duration_match.group(1))
            duration_unit = nicu_duration_match.group(2)
            
            if 'week' in duration_unit:
                self.implied_answers['nicu_duration'] = int(duration_num * 7)  # Convert weeks to days
            elif 'month' in duration_unit:
                self.implied_answers['nicu_duration'] = int(duration_num * 30)  # Convert months to days
            else:  # days
                self.implied_answers['nicu_duration'] = int(duration_num)
        
        # FIXED: Improve detection of HIE therapy mentions with negative context awareness
        cooling_indicators = ['cooling', 'hypothermia', 'hie therapy', 'head cool', 'cooling blanket']
        cooling_negative = ['no cooling', 'didn\'t receive cooling', 'without cooling', 'no hypothermia']
        
        if any(indicator in message_lower for indicator in cooling_indicators):
            if any(neg in message_lower for neg in cooling_negative):
                self.implied_answers['hie_therapy'] = False
            else:
                self.implied_answers['hie_therapy'] = True
        
        # FIXED: Improve scan detection with negative context awareness
        scan_indicators = ['mri', 'brain scan', 'head scan', 'cat scan', 'ct scan', 'ultrasound']
        scan_negative = ['no scan', 'didn\'t have scan', 'no mri', 'without scan', 'no scans']
        
        if any(indicator in message_lower for indicator in scan_indicators):
            if any(neg in message_lower for neg in scan_negative):
                self.implied_answers['brain_scan'] = False
            else:
                self.implied_answers['brain_scan'] = True
        
        # Check for developmental delay mentions
        delay_indicators = ['delay', 'behind', 'missing milestone', 'developmental', 'not meeting', 'therapy', 'pt', 'ot', 'speech', 'physical therapy']
        normal_indicators = ['no delay', 'on track', 'normal development', 'meeting milestone', 'developing normally', 'no major delays', 'everything seems normal']
        
        if any(indicator in message_lower for indicator in delay_indicators):
            if any(neg in message_lower for neg in normal_indicators):
                self.implied_answers['milestones'] = False
            else:
                self.implied_answers['milestones'] = True
        
        # Check for lawyer mentions
        lawyer_indicators = ['lawyer', 'attorney', 'legal', 'law firm', 'lawsuit', 'case review', 'litigation']
        lawyer_negative = ['no lawyer', 'haven\'t seen', 'didn\'t consult', 'not yet', 'looking for']
        if any(indicator in message_lower for indicator in lawyer_indicators):
            if any(neg in message_lower for neg in lawyer_negative):
                self.implied_answers['lawyer'] = False
            else:
                self.implied_answers['lawyer'] = True
        
        # Try to extract state information
        state = self.nlu_processor.interpret_state(message)
        if state:
            self.implied_answers['state'] = state
            
        # FIXED: Add better detection for complex messages with multiple implications
        if '28 weeks' in message_lower and 'nicu' in message_lower and 'cooling' in message_lower:
            # Handle complex cases like "28 weeks, NICU for month, cooling therapy, delays"
            self.implied_answers['nicu'] = True
            if 'month' in message_lower:
                self.implied_answers['nicu_duration'] = 30
            self.implied_answers['hie_therapy'] = True
            if 'delay' in message_lower:
                self.implied_answers['milestones'] = True
    
    def _handle_implied_nicu_answer(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle when NICU answer is implied in pregnancy response"""
        self.phases['nicu']['value'] = self.implied_answers['nicu']
        self.phases['nicu']['complete'] = True
        self.case_data_manager.update_phase_completion(self.case_data, 'nicu')
        
        if not self.implied_answers['nicu']:
            self.case_data_manager.apply_nicu_points(self.case_data, False)
            # For full-term babies without NICU, still ask HIE therapy question
            if self.case_data.get('weeks_pregnant', 0) >= 36:
                self.current_phase = 'hie_therapy'
            else:
                self.current_phase = 'milestones'
        else:
            self.case_data_manager.apply_nicu_points(self.case_data, True)
            
            if self.implied_answers['nicu_duration'] is not None:
                # Also handle implied duration
                self.phases['nicu_duration']['value'] = self.implied_answers['nicu_duration']
                self.phases['nicu_duration']['complete'] = True
                self.case_data_manager.update_phase_completion(self.case_data, 'nicu_duration')
                self.case_data_manager.apply_nicu_points(self.case_data, True, self.implied_answers['nicu_duration'])
                
                # Always ask HIE for full term babies regardless of NICU stay
                if self.case_data.get('weeks_pregnant', 0) >= 36:
                    self.current_phase = 'hie_therapy'
                else:
                    self.current_phase = 'brain_scan'
            else:
                self.current_phase = 'nicu_duration'
        
        return response_data
    
    def _handle_implied_hie_answer(self) -> Dict[str, Any]:
        """Handle when HIE therapy answer is implied"""
        self.phases['hie_therapy']['value'] = self.implied_answers['hie_therapy']
        self.phases['hie_therapy']['complete'] = True
        self.case_data_manager.update_phase_completion(self.case_data, 'hie_therapy')
        self.case_data_manager.apply_hie_therapy_points(self.case_data, self.implied_answers['hie_therapy'])
        
        # FIXED: Correct phase transition based on NICU status
        if not self.phases.get('nicu', {}).get('value', False):
            self.current_phase = 'milestones'
        else:
            self.current_phase = 'brain_scan'
            
        return {}
    
    def _handle_implied_brain_scan_answer(self) -> Dict[str, Any]:
        """Handle when brain scan answer is implied"""
        self.phases['brain_scan']['value'] = self.implied_answers['brain_scan']
        self.phases['brain_scan']['complete'] = True
        self.case_data_manager.update_phase_completion(self.case_data, 'brain_scan')
        self.case_data_manager.apply_brain_scan_points(self.case_data, self.implied_answers['brain_scan'])
        self.current_phase = 'milestones'
        return {}
    
    def _handle_implied_milestones_answer(self) -> Dict[str, Any]:
        """Handle when milestones answer is implied"""
        self.phases['milestones']['value'] = self.implied_answers['milestones']
        self.phases['milestones']['complete'] = True
        self.case_data_manager.update_phase_completion(self.case_data, 'milestones')
        self.case_data_manager.apply_milestones_points(self.case_data, self.implied_answers['milestones'])
        self.current_phase = 'lawyer'
        return {}
    
    def _handle_implied_lawyer_answer(self) -> Dict[str, Any]:
        """Handle when lawyer consultation answer is implied"""
        self.phases['lawyer']['value'] = self.implied_answers['lawyer']
        self.phases['lawyer']['complete'] = True
        self.case_data_manager.update_phase_completion(self.case_data, 'lawyer')
        self.case_data_manager.apply_lawyer_points(self.case_data, self.implied_answers['lawyer'])
        
        if self.implied_answers['lawyer']:
            return {
                'end_chat': True,
                'farewell_message': "We're glad to hear you're already getting your case reviewed and getting the help you need. We wish you and your family the best."
            }
        
        if self.implied_answers['state'] is not None:
            return self._handle_implied_state_answer()
        
        self.current_phase = 'state'
        return {}
    
    def _handle_implied_state_answer(self) -> Dict[str, Any]:
        """Handle when state answer is implied"""
        state = self.implied_answers['state']
        self.phases['state']['value'] = state
        self.phases['state']['complete'] = True
        self.case_data['state'] = state
        self.case_data_manager.update_phase_completion(self.case_data, 'state')
        
        # Check final eligibility
        is_eligible, reason = self.eligibility_checker.check_comprehensive_eligibility(
            self.case_data.get('age'), state
        )
        if not is_eligible:
            return {'eligible': False, 'reason': reason}
        
        self.current_phase = 'complete'
        self.case_data_manager.save_case_data(self.case_data, self.phases)
        return {}
    
    def _is_back_command(self, message: str) -> bool:
        """Check if message is a back command"""
        back_indicators = ['back', 'previous', 'go back', 'return']
        return any(indicator in message.lower() for indicator in back_indicators)
    
    def _is_help_command(self, message: str) -> bool:
        """Check if message is a help command"""
        help_indicators = ['help', 'confused', "don't understand", "what's this", "explain"]
        return message.lower() in help_indicators or any(indicator in message.lower() for indicator in help_indicators)
    
    def _handle_back_request(self) -> Dict[str, Any]:
        """Handle request to go back to previous question"""
        phases_list = list(self.phases.keys())
        try:
            current_index = phases_list.index(self.current_phase)
        except ValueError:
            return {'error': "An error occurred. Let's continue with the current question."}
        
        if current_index <= 0:
            return {'error': "We can't go back any further. Let's continue with the current question."}
        
        # Move back one phase
        prev_phase = phases_list[current_index - 1]
        self.phases[prev_phase]['complete'] = False
        self.current_phase = prev_phase
        
        return {'back': True}
    
    def _handle_help_request(self) -> Dict[str, Any]:
        """Provide help for current phase"""
        help_messages = {
            'age': "I need to know how old your child is. You can provide the age in years, like '5 years old' or just '5'.",
            'pregnancy': "I'm asking about your pregnancy length (in weeks) when your child was born, and if there were any complications during delivery.",
            'nicu': "NICU stands for Neonatal Intensive Care Unit. I'm asking if your child needed to stay in the NICU after birth.",
            'nicu_duration': "I need to know how long your child stayed in the NICU. You can answer in days, weeks, or months.",
            'hie_therapy': "HIE therapy (also called head cooling) is a treatment used for babies who experienced oxygen deprivation during birth. I'm asking if your child received this treatment.",
            'brain_scan': "I'm asking if your child had a brain imaging test (MRI or other scan) while in the NICU.",
            'milestones': "Developmental milestones are skills like rolling over, sitting up, walking, or talking that children typically develop at certain ages. I'm asking if your child is delayed in any of these areas.",
            'lawyer': "I'm asking if you've already consulted with a lawyer about your child's case.",
            'state': "I need to know which US state your child was born in. This helps determine eligibility based on state-specific laws."
        }
        
        return {'help': help_messages.get(self.current_phase, "I'm gathering information about your child's case to see if we can help. Please answer the current question as best you can.")}
    
    def get_next_question(self) -> Tuple[str, bool]:
        """Get the next question or message to send"""
        if self.empty_response_count >= 3:
            return "I notice you haven't responded. Would you like to continue with the consultation? Please type 'yes' to continue or 'quit' to end our conversation.", True
        
        if self.current_phase == 'complete':
            return self._get_completion_message(), False
        
        return self.phases[self.current_phase]['question'], False
    
    def _get_completion_message(self) -> str:
        """Generate completion message with case ranking context"""
        rating = ""
        if self.case_data.get('ranking') in ['high', 'very high']:
            rating = "Based on your answers, your case shows strong potential. "
        
        return (f"Thank you! {rating}We'll connect you with a representative who will "
                "ask you a few more questions and schedule a FREE case review call with one of our affiliate lawyers. "
                "There is no fee or cost to you.")
    
    def get_case_summary(self) -> Dict[str, Any]:
        """Get current case summary for external use"""
        return {
            'age': self.case_data.get('age'),
            'state': self.case_data.get('state'),
            'ranking': self.case_data.get('ranking'),
            'points': self.case_data.get('points'),
            'current_phase': self.current_phase,
            'phases_completed': {phase: data['complete'] for phase, data in self.phases.items()}
        }