import logging
import re
from typing import List, Set, Optional

try:
    # Prefer absolute import when module is executed directly (script context)
    from criteria_parser import CriteriaParser
except Exception:
    # Fallback to package-relative import when used as a package
    from .criteria_parser import CriteriaParser

logger = logging.getLogger(__name__)

class FeasibilityScorer:
    def __init__(self):
        self.parser = CriteriaParser()
        self.umls = None
        self._umls_load_attempted = False
    
    def _get_umls(self):
        """Lazy-load UMLS only when needed"""
        if not self._umls_load_attempted:
            self._umls_load_attempted = True
            try:
                from .umls_linker import UMLSLinker
                self.umls = UMLSLinker()
                logger.info("UMLS Linker loaded in FeasibilityScorer")
            except Exception as e:
                logger.warning(f"Could not load UMLSLinker: {e}")
                self.umls = None
        return self.umls

    def extract_cuis(self, text_list: List[str]) -> Set[str]:
        """Helper to extract CUIs from a list of strings using the lazy-loaded linker."""
        umls = self._get_umls()
        if not umls:
            return set()
        cuis = set()
        for text in text_list:
            cuis.update(umls.extract_cuis(text))
        return cuis

    def score_patient(
        self,
        patient_profile: dict,
        trial_criteria_text: str,
        trial_metadata: Optional[dict] = None,
        patient_cuis: Optional[Set[str]] = None
    ) -> dict:
        """
        Input:
            patient_profile (dict): {
                "age": 65, "gender": "Female", "ecog": 1,
                "conditions": ["NSCLC"], "biomarkers": ["EGFR"],
                "labs": {"Creatinine": 1.2, "Bilirubin": 0.8}
            }
            trial_criteria_text (str): Raw text from database
            trial_metadata (dict): Structured DB columns (min_age, sex, etc.)
        """
        # 1. Try to use cached parsed_criteria from database (FAST)
        # If not available, fallback to parsing (SLOW)
        db_conditions = []
        db_cuis = []
        
        if trial_metadata and trial_metadata.get('parsed_criteria'):
            # Use pre-computed parsed data (instant)
            trial_data = trial_metadata['parsed_criteria']
            logger.debug("Using cached parsed_criteria for trial")
        else:
            # Fallback: Parse on-the-fly (slow, for trials without cached data)
            trial_data = self.parser.parse(trial_criteria_text)
            logger.debug("Parsing trial criteria on-the-fly (no cache)")
        
        # 2. Override with DB metadata if available
        if trial_metadata:
            # Override Age if DB has it
            db_min_age = trial_metadata.get('min_age_years')
            db_max_age = trial_metadata.get('max_age_years')
            
            if db_min_age is not None:
                trial_data['age_range'][0] = float(db_min_age)
            if db_max_age is not None:
                trial_data['age_range'][1] = float(db_max_age)
            
            # Override Gender if DB has it
            db_sex = trial_metadata.get('sex')
            if db_sex:
                if db_sex.upper() == "MALE": trial_data['gender'] = "Male"
                elif db_sex.upper() == "FEMALE": trial_data['gender'] = "Female"
                else: trial_data['gender'] = "All"
            
            # Conditions from DB
            db_conditions = trial_metadata.get('conditions', [])
            db_cuis = trial_metadata.get('conditions_cuis', [])
        
        score = 0
        reasons = []
        is_feasible = True
        
        # 1. HARD EXCLUSIONS
        patient_conditions = set(patient_profile.get('conditions', []))
        parsed_exclusions = trial_data.get('exclusions', [])
        patient_history = set(patient_profile.get('history', []))
        all_patient_issues = patient_conditions.union(patient_history)
        
        for exclusion in parsed_exclusions:
            if exclusion in all_patient_issues:
                return self._compile_result(0, False, [f" Hard Exclusion: Patient has '{exclusion}'"], trial_data)

        # 2. CONDITION MATCHING (Must treat the right disease)
        parsed_conditions = set(trial_data['conditions'])
        structured_conditions = set(db_conditions)
        all_trial_indications = parsed_conditions.union(structured_conditions)
        
        if not patient_conditions:
            
            score += 5
            reasons.append(" No patient conditions provided - relevance unclear")
        else:
            # Check for overlap with fuzzy matching
            patient_cond_lower = {c.lower() for c in patient_conditions}
            trial_cond_lower = {c.lower() for c in all_trial_indications}
            
            # Fuzzy intersection logic
            match_found = False
            matched_names = []
            
            # --- UMLS MATCHING START ---
            umls = self._get_umls()
            if umls:
                # Extract CUIs from patient conditions if not provided
                if patient_cuis is None:
                    patient_cuis = set()
                    for pc in patient_conditions:
                        patient_cuis.update(umls.extract_cuis(pc))
                
                # Use pre-computed trial CUIs from DB if available
                trial_cuis = set(db_cuis)
                
                # Fallback: Extract from text if DB is empty (e.g. old data)
                # DISABLED FOR PERFORMANCE: This runs 500x per query if DB is empty.
                # if not trial_cuis:
                #     for tc in all_trial_indications:
                #         trial_cuis.update(umls.extract_cuis(tc))
                
                # Check intersection
                common_cuis = patient_cuis.intersection(trial_cuis)
                if common_cuis:
                    match_found = True
                    matched_names.append(f"UMLS Match (CUIs: {list(common_cuis)})")
            # --- UMLS MATCHING END ---

            # Fallback to string matching if UMLS fails or finds nothing
            if not match_found:
                for p_cond in patient_cond_lower:
                    for t_cond in trial_cond_lower:
            
                        if p_cond in t_cond or t_cond in p_cond:
                            match_found = True
                            matched_names.append(t_cond)
            
            if match_found:
                score += 40
                reasons.append(f" Condition Match: {list(set(matched_names))}")
            else:
                is_feasible = False
                score += 0
                reasons.append(f" Condition Mismatch: Patient has {list(patient_conditions)}, Trial is for {list(all_trial_indications)[:3]}")

        # 3. BIOMARKER MATCHING (High Reward) 
        patient_bios = set(patient_profile.get('biomarkers', []))
        trial_bios = set(trial_data['biomarkers'])
        
        common_bios = patient_bios.intersection(trial_bios)
        if common_bios:
            score += 25
            reasons.append(f" Biomarker Match: {list(common_bios)}")

        # 4. ECOG CHECK
        if trial_data['ecog'] and 'ecog' in patient_profile:
            patient_ecog = patient_profile['ecog']
            if patient_ecog is not None:
                if patient_ecog in trial_data['ecog']:
                    score += 15
                    reasons.append(f" ECOG {patient_ecog} is allowed")
                else:
                    is_feasible = False
                    reasons.append(f" ECOG {patient_ecog} excluded (Trial needs: {trial_data['ecog']})")

        # 5. LAB THRESHOLDS (The Math) 
        lab_points = 0
        lab_failures = 0
        patient_labs = patient_profile.get('labs', {})
        trial_labs = trial_data.get('labs', {})
        
        for lab_name, rule in trial_labs.items():
            if lab_name in patient_labs:
                val = patient_labs[lab_name]
                if val is None:
                    continue
                threshold = rule['value']
                op = rule['operator']
                
                # Check Inequality
                passed = False
                if op == '>' and val > threshold: passed = True
                elif op == '>=' and val >= threshold: passed = True
                elif op == '<' and val < threshold: passed = True
                elif op == '<=' and val <= threshold: passed = True
                
                if passed:
                    lab_points += 5
                    reasons.append(f" Lab Passed: {lab_name} {val} {op} {threshold}")
                else:
                    lab_failures += 1
                    is_feasible = False
                    reasons.append(f" Lab Failed: {lab_name} {val} NOT {op} {threshold}")
        
        score += min(lab_points, 15)
        
        if lab_failures > 0:
            reasons.append(f" {lab_failures} critical lab(s) failed - patient ineligible")

        # 6. AGE & GENDER 
        p_age = patient_profile.get('age')
        min_a, max_a = trial_data['age_range']
        if p_age is not None:
            if min_a <= p_age <= max_a:
                score += 5
                reasons.append(f" Age {p_age} matched")
            else:
                is_feasible = False
                reasons.append(f" Age {p_age} outside [{min_a}-{max_a}]")

        # 7. PRIOR LINES OF THERAPY
        p_lines = patient_profile.get('prior_lines')
        if p_lines is not None:
            # Regex for "at least X prior lines" or "received X prior lines"
            # Matches: "received at least 2 prior lines", ">= 1 prior line"
            min_lines_match = re.search(r'(?:received|at least|>=?)\s*(\d+)\s*(?:prior|previous)\s*lines?', trial_criteria_text, re.IGNORECASE)
            
            # Regex for "no more than X prior lines" or "up to X prior lines"
            max_lines_match = re.search(r'(?:no more than|up to|<=?)\s*(\d+)\s*(?:prior|previous)\s*lines?', trial_criteria_text, re.IGNORECASE)

            if min_lines_match:
                required_min = int(min_lines_match.group(1))
                if p_lines >= required_min:
                    score += 10
                    reasons.append(f" Prior Lines {p_lines} >= {required_min} (Matched)")
                else:
                    is_feasible = False
                    reasons.append(f" Prior Lines {p_lines} < {required_min} (Trial requires at least {required_min})")
            
            if max_lines_match:
                limit_max = int(max_lines_match.group(1))
                if p_lines <= limit_max:
                    score += 10
                    reasons.append(f" Prior Lines {p_lines} <= {limit_max} (Matched)")
                else:
                    is_feasible = False
                    reasons.append(f" Prior Lines {p_lines} > {limit_max} (Trial limit is {limit_max})")

        p_gender = patient_profile.get('gender')
        t_gender = trial_data['gender']
        if p_gender:
            p_gender = p_gender.capitalize()
            if t_gender == "All":
                score += 5
                reasons.append(f"Gender matched (Trial open to All)")
            
            elif p_gender == t_gender:
                score += 5
                reasons.append(f"Gender {p_gender} matched")
                
            else:
                reasons.append(f"Gender Mismatch: Patient {p_gender} vs Trial {t_gender}")
                is_feasible = False
       
        
        # 7. TEMPORAL WASHOUTS
        p_washout = patient_profile.get('days_since_last_treatment')
        temporal = trial_data.get('temporal', {})
        t_washout = temporal.get('chemo_washout') if temporal else None
        
        if p_washout is not None and t_washout is not None:
            if p_washout >= t_washout:
                score += 5
                reasons.append(f"Washout Cleared: {p_washout}d > {t_washout}d")
            else:
                is_feasible = False 
                reasons.append(f"Washout Fail: Only {p_washout} days (Needs {t_washout})")

        # 8. LINES OF THERAPY
        p_lines = patient_profile.get('prior_lines')
        lines_rule = trial_data.get('lines_of_therapy', {'min': 0, 'max': 999})
        
        if p_lines is not None and lines_rule:
            if lines_rule['min'] <= p_lines <= lines_rule['max']:
                score += 10
                reasons.append(f"Lines of Therapy: {p_lines} (Allowed: {lines_rule['min']}-{lines_rule['max']})")
            else:
                is_feasible = False
                reasons.append(f"Lines Fail: Patient has {p_lines}, Trial needs {lines_rule['min']}-{lines_rule['max']}")

        return self._compile_result(score, is_feasible, reasons, trial_data)

    # ... inside FeasibilityScorer class ...

    def _compile_result(self, score, is_feasible, reasons, trial_data):
        # FIX: Enforce a "Relevance Threshold"
        # If the score is too low (e.g., < 40), it means we didn't match 
        # the Condition (+30) or the Biomarker (+20).
        # A trial with only Age/Gender matching is NOT useful.
        
        #if score < 40:
        #    is_feasible = False
        #    if not any("Condition Mismatch" in r for r in reasons):
        #        reasons.append("Low Relevance: No Condition or Biomarker match found.")

        # If infeasible, force score to 0 so it drops to the bottom
        final_score = min(score, 100) if is_feasible else 0
        
        logger.debug(
            "Feasibility result: score=%s final_score=%s feasible=%s reasons=%s",
            score, final_score, is_feasible, reasons
        )

        return {
            "score": final_score,
            "is_feasible": is_feasible,
            "reasons": reasons,
            "parsed_criteria": trial_data
        }
