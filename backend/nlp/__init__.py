# backend/nlp/__init__.py

from .criteria_parser import CriteriaParser
from .feasibility_scorer import FeasibilityScorer

# Initialize singleton instances to save memory
# (Loading spaCy takes time, so we only want to do it once)
_scorer = FeasibilityScorer()

def rank_trials(patient_profile, trials_list):
    """
    Main API Entry Point for the Search Engine.
    
    Args:
        patient_profile (dict): The user's data.
        trials_list (list): List of dicts from the database/search engine.
                            Must contain [{'nct_id': '...', 'eligibility_criteria_raw': '...'}, ...]
    
    Returns:
        list: The same trials, sorted by score (descending), with 'score' and 'reasons' added.
    """
    scored_trials = []
    
    for trial in trials_list:
        # Handle different database column names just in case
        #print(trial.keys())
        text = trial.get('eligibility_criteria_raw') or trial.get('criteria') or ""

        #Get Metadata
        metadata = {
            "min_age_years": trial.get("min_age_years"),
            "max_age_years": trial.get("max_age_years"),
            "sex": trial.get("sex"),
            "conditions": trial.get("conditions") or []
        }

        if not text and not any(metadata.values()):
            # NO text and NO metadata, skip or fail
            trial['feasibility_score'] = 0
            trial['feasibility_reasons'] = ["No data available"]
            trial['is_feasible'] = False
            trial['parsed_criteria'] = {}
            scored_trials.append(trial)
            continue

        #run scorer logic
        result = _scorer.score_patient(patient_profile, text, trial_metadata=metadata)
        
        # Enrich the trial object
        trial['feasibility_score'] = result['score']
        trial['feasibility_reasons'] = result['reasons']
        trial['is_feasible'] = result['is_feasible']
        trial['parsed_criteria'] = result['parsed_criteria'] # Optional: For debugging/UI
        
        scored_trials.append(trial)
    
    # Sort by score (highest first)
    scored_trials.sort(key=lambda x: x['feasibility_score'], reverse=True)
    
    return scored_trials