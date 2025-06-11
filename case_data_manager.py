import json
import os
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from config_manager import config

class CaseDataManager:
    """
    Manages case data persistence, ranking calculations, and file operations.
    Preserves all functionality from the original ConversationManager case data handling.
    """
    
    def __init__(self):
        self.logger = config.get_logger("CaseDataManager")
        self.data_directory = config.data_directory
        config.ensure_directory_exists(self.data_directory)
        
        # Point system thresholds (preserved from original)
        self.ranking_thresholds = {
            'very high': 80,
            'high': 65,
            'normal': 40,
            'low': 0
        }
    
    def initialize_case_data(self) -> Dict[str, Any]:
        """
        Initialize a new case with default values.
        Preserves original case_data structure from ConversationManager.
        """
        return {
            'age': None,
            'state': None,
            'weeks_pregnant': 0,
            'difficult_delivery': False,
            'points': 50,  # Starting baseline score
            'ranking': 'normal',
            'timestamp': datetime.now().isoformat(),
            # Phase completion tracking
            'phases_completed': {
                'age': False,
                'pregnancy': False,
                'nicu': False,
                'nicu_duration': False,
                'hie_therapy': False,
                'brain_scan': False,
                'milestones': False,
                'lawyer': False,
                'state': False
            }
        }
    
    def update_points(self, case_data: Dict[str, Any], points_change: int, reason: str) -> None:
        """
        Update case points based on medical factors and recalculate ranking.
        Preserves exact logic from original ConversationManager.update_points()
        """
        try:
            points_change = int(points_change)
        except (ValueError, TypeError):
            self.logger.warning(f"Invalid points change value: {points_change}. Using 0.")
            points_change = 0
        
        case_data['points'] += points_change
        self.logger.info(f"Points {'+' if points_change >= 0 else ''}{points_change} ({reason}). New total: {case_data['points']}")
        
        # Ensure points don't go negative
        if case_data['points'] < 0:
            case_data['points'] = 0
            self.logger.info("Points adjusted to minimum of 0")
        
        # Update ranking based on point thresholds
        new_rank = self._calculate_ranking(case_data['points'])
        if new_rank != case_data.get('ranking'):
            case_data['ranking'] = new_rank
            self.logger.info(f"Case ranking updated to: {new_rank}")
    
    def _calculate_ranking(self, points: int) -> str:
        """Calculate ranking based on point total"""
        for rank in ['very high', 'high', 'normal', 'low']:
            if points >= self.ranking_thresholds[rank]:
                return rank
        return 'low'
    
    def apply_pregnancy_points(self, case_data: Dict[str, Any], weeks: Optional[int], difficult_delivery: bool) -> None:
        """
        Apply points based on pregnancy-related factors.
        Preserves original scoring logic.
        """
        if weeks is not None:
            case_data['weeks_pregnant'] = weeks
            
            if weeks < 30:
                self.update_points(case_data, 15, "Very premature birth (< 30 weeks)")
            elif weeks < 36:
                self.update_points(case_data, 10, "Premature birth (< 36 weeks)")
            else:
                self.update_points(case_data, -5, "Full term birth (>= 36 weeks)")
        
        case_data['difficult_delivery'] = difficult_delivery
        if difficult_delivery:
            self.update_points(case_data, 15, "Difficult delivery reported")
        else:
            self.update_points(case_data, -10, "No difficult delivery reported")
    
    def apply_nicu_points(self, case_data: Dict[str, Any], had_nicu: bool, duration_days: Optional[int] = None) -> None:
        """
        Apply points based on NICU stay information.
        Preserves original scoring logic.
        """
        if not had_nicu:
            self.update_points(case_data, -15, "No NICU stay")
            return
        
        self.update_points(case_data, 10, "NICU stay required")
        
        if duration_days is not None and duration_days > 0:
            if duration_days > 30:
                self.update_points(case_data, 15, "Extended NICU stay (>30 days)")
            elif duration_days > 14:
                self.update_points(case_data, 10, "Moderate NICU stay (>14 days)")
            elif duration_days > 7:
                self.update_points(case_data, 5, "Short NICU stay (>7 days)")
            else:
                self.update_points(case_data, 3, "Brief NICU stay")
    
    def apply_hie_therapy_points(self, case_data: Dict[str, Any], received_hie: bool) -> None:
        """Apply points for HIE/cooling therapy (highest indicator)"""
        if received_hie:
            self.update_points(case_data, 40, "Received HIE/head cooling therapy")
    
    def apply_brain_scan_points(self, case_data: Dict[str, Any], had_scan: bool) -> None:
        """Apply points for brain scan/MRI evidence"""
        if had_scan:
            self.update_points(case_data, 20, "Brain scan/MRI was performed")
        else:
            self.update_points(case_data, -10, "No brain scan/MRI performed")
    
    def apply_milestones_points(self, case_data: Dict[str, Any], has_delays: bool) -> None:
        """Apply points for developmental milestone delays"""
        if has_delays:
            self.update_points(case_data, 15, "Developmental delays reported")
        else:
            self.update_points(case_data, -5, "No developmental delays reported")
    
    def apply_lawyer_points(self, case_data: Dict[str, Any], prev_consultation: bool) -> None:
        """Apply points for previous legal consultation"""
        if prev_consultation:
            self.update_points(case_data, -5, "Previous legal consultation")
        else:
            self.update_points(case_data, 5, "No previous legal consultation")
    
    def update_phase_completion(self, case_data: Dict[str, Any], phase: str, completed: bool = True) -> None:
        """Track completion of conversation phases"""
        if 'phases_completed' not in case_data:
            case_data['phases_completed'] = {}
        case_data['phases_completed'][phase] = completed
    
    def save_case_data(self, case_data: Dict[str, Any], phases: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Save case data to JSON files with comprehensive question summary.
        Enhanced to include all answers and implied responses at the top.
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Create comprehensive question summary
            question_summary = {
                'child_age': case_data.get('age'),
                'weeks_pregnant': case_data.get('weeks_pregnant'),
                'difficult_delivery': case_data.get('difficult_delivery'),
                'nicu_stay': phases.get('nicu', {}).get('value'),
                'nicu_duration': phases.get('nicu_duration', {}).get('value'),
                'hie_therapy': phases.get('hie_therapy', {}).get('value'),
                'brain_scan': phases.get('brain_scan', {}).get('value'),
                'developmental_delays': phases.get('milestones', {}).get('value'),
                'previous_lawyer': phases.get('lawyer', {}).get('value'),
                'birth_state': case_data.get('state')
            }
            
            # Prepare complete data structure with summary at top
            save_data = {
                'case_summary': question_summary,
                'case_assessment': {
                    'ranking': case_data.get('ranking', 'normal'),
                    'points': case_data.get('points', 50),
                    'eligible': True  # If we reached save, case was eligible
                },
                'timestamp': timestamp,
                'detailed_responses': {
                    'age_response': phases.get('age', {}).get('value'),
                    'pregnancy_response': phases.get('pregnancy', {}).get('value'),
                    'nicu_response': phases.get('nicu', {}).get('value'),
                    'nicu_duration_response': phases.get('nicu_duration', {}).get('value'),
                    'hie_therapy_response': phases.get('hie_therapy', {}).get('value'),
                    'brain_scan_response': phases.get('brain_scan', {}).get('value'),
                    'milestones_response': phases.get('milestones', {}).get('value'),
                    'lawyer_response': phases.get('lawyer', {}).get('value'),
                    'state_response': phases.get('state', {}).get('value')
                },
                'phases_completed': case_data.get('phases_completed', {}),
                'raw_case_data': {
                    'age': case_data.get('age'),
                    'state': case_data.get('state'),
                    'weeks_pregnant': case_data.get('weeks_pregnant', 0),
                    'difficult_delivery': case_data.get('difficult_delivery', False)
                }
            }
            
            # Save individual case file
            filename = os.path.join(self.data_directory, f"case_{timestamp}.json")
            with open(filename, 'w') as f:
                json.dump(save_data, f, indent=2)
            
            # Update aggregate file
            self._update_aggregate_file(save_data)
            
            self.logger.info(f"Case data saved successfully to {filename}")
            return True, None
            
        except PermissionError:
            error_msg = "Permission denied when saving case data"
            self.logger.error(error_msg)
            return False, error_msg
        except IOError as e:
            error_msg = f"I/O error when saving case data: {e}"
            self.logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error saving case data: {e}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def _update_aggregate_file(self, case_data: Dict[str, Any]) -> None:
        """Update the aggregate cases file with new case data"""
        aggregate_file = os.path.join(self.data_directory, "all_cases.json")
        
        try:
            # Load existing data
            if os.path.exists(aggregate_file):
                with open(aggregate_file, 'r') as f:
                    existing_data = json.load(f)
                    
                # Ensure existing data is a list
                if not isinstance(existing_data, list):
                    existing_data = [existing_data]
            else:
                existing_data = []
            
            # Add new case
            existing_data.append(case_data)
            
            # Save updated data
            with open(aggregate_file, 'w') as f:
                json.dump(existing_data, f, indent=2)
                
            self.logger.info(f"Updated aggregate file: {aggregate_file}")
            
        except Exception as e:
            self.logger.error(f"Error updating aggregate file: {e}")
    
    def load_case_data(self, timestamp: str) -> Optional[Dict[str, Any]]:
        """Load specific case data by timestamp"""
        try:
            filename = os.path.join(self.data_directory, f"case_{timestamp}.json")
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading case data for {timestamp}: {e}")
        return None
    
    def get_all_cases(self) -> list:
        """Retrieve all stored cases from aggregate file"""
        aggregate_file = os.path.join(self.data_directory, "all_cases.json")
        try:
            if os.path.exists(aggregate_file):
                with open(aggregate_file, 'r') as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else [data]
        except Exception as e:
            self.logger.error(f"Error loading all cases: {e}")
        return []
    
    def get_cases_by_ranking(self, ranking: str) -> list:
        """Get all cases with specific ranking"""
        all_cases = self.get_all_cases()
        return [case for case in all_cases if case.get('ranking') == ranking]
    
    def get_case_statistics(self) -> Dict[str, Any]:
        """Generate basic statistics about saved cases"""
        all_cases = self.get_all_cases()
        
        if not all_cases:
            return {'total': 0}
        
        rankings = {}
        states = {}
        
        for case in all_cases:
            ranking = case.get('ranking', 'unknown')
            rankings[ranking] = rankings.get(ranking, 0) + 1
            
            state = case.get('state', 'unknown')
            states[state] = states.get(state, 0) + 1
        
        return {
            'total': len(all_cases),
            'by_ranking': rankings,
            'by_state': states,
            'average_points': sum(case.get('points', 0) for case in all_cases) / len(all_cases)
        }