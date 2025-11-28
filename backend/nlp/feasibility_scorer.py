try:
    # Prefer absolute import when module is executed directly (script context)
    from criteria_parser import CriteriaParser
except Exception:
    # Fallback to package-relative import when used as a package
    from .criteria_parser import CriteriaParser

class FeasibilityScorer:
    def __init__(self):
        self.parser = CriteriaParser()

    def score_patient(self, patient_profile, trial_criteria_text):
        """
        Input:
            patient_profile (dict): {
                "age": 65, "gender": "Female", "ecog": 1,
                "conditions": ["NSCLC"], "biomarkers": ["EGFR"],
                "labs": {"Creatinine": 1.2, "Bilirubin": 0.8}
            }
            trial_criteria_text (str): Raw text from database
        """
        # 1. Parse the trial text
        trial_data = self.parser.parse(trial_criteria_text)
        
        score = 0
        reasons = []
        is_feasible = True
        
        # 1. HARD EXCLUSIONS (The "Deal Breakers") 
        # If trial excludes 'Pregnancy' and patient has 'Pregnancy' -> Fail immediately
        patient_conditions = set(patient_profile.get('conditions', []))
        parsed_exclusions = trial_data.get('exclusions', [])
        
        for exclusion in parsed_exclusions:
            if exclusion in patient_conditions:
                return self._compile_result(0, False, [f" Hard Exclusion: Patient has '{exclusion}'"], trial_data)

        # 2. CONDITION MATCHING (Must treat the right disease)
        trial_conditions = set(trial_data['conditions'])
        if trial_conditions:
            common = patient_conditions.intersection(trial_conditions)
            if common:
                score += 30
                reasons.append(f" Condition Match: {list(common)}")
            else:
                # Soft Fail: If trial specifies a disease and patient doesn't have it
                is_feasible = False
                reasons.append(f" Condition Mismatch: Trial is for {list(trial_conditions)}")

        # 3. BIOMARKER MATCHING (High Reward) 
        patient_bios = set(patient_profile.get('biomarkers', []))
        trial_bios = set(trial_data['biomarkers'])
        
        common_bios = patient_bios.intersection(trial_bios)
        if common_bios:
            score += 20
            reasons.append(f" Biomarker Match: {list(common_bios)}")

        # 4. ECOG CHECK
        # If trial requires ECOG 0-1 and patient is 2 -> Fail
        if trial_data['ecog'] and 'ecog' in patient_profile:
            patient_ecog = patient_profile['ecog']
            if patient_ecog in trial_data['ecog']:
                score += 10
                reasons.append(f" ECOG {patient_ecog} is allowed")
            else:
                is_feasible = False
                reasons.append(f" ECOG {patient_ecog} excluded (Trial needs: {trial_data['ecog']})")

        #5. LAB THRESHOLDS (The Math) 
        patient_labs = patient_profile.get('labs', {})
        trial_labs = trial_data.get('labs', {})
        
        for lab_name, rule in trial_labs.items():
            if lab_name in patient_labs:
                val = patient_labs[lab_name]
                threshold = rule['value']
                op = rule['operator']
                
                # Check Inequality
                passed = False
                if op == '>' and val > threshold: passed = True
                elif op == '>=' and val >= threshold: passed = True
                elif op == '<' and val < threshold: passed = True
                elif op == '<=' and val <= threshold: passed = True
                
                if passed:
                    score += 10
                    reasons.append(f" Lab Passed: {lab_name} {val} {op} {threshold}")
                else:
                    is_feasible = False
                    reasons.append(f" Lab Failed: {lab_name} {val} NOT {op} {threshold}")

        # 6. AGE & GENDER 
        p_age = patient_profile.get('age')
        min_a, max_a = trial_data['age_range']
        if p_age is not None:
            if min_a <= p_age <= max_a:
                score += 5
            else:
                is_feasible = False
                reasons.append(f" Age {p_age} outside [{min_a}-{max_a}]")

        p_gender = patient_profile.get('gender')
        t_gender = trial_data['gender']
        if p_gender and t_gender != "All" and p_gender != t_gender:
            is_feasible = False
            reasons.append(f" Gender Mismatch: Patient {p_gender} vs Trial {t_gender}")
        
        # 7. TEMPORAL WASHOUTS
        p_washout = patient_profile.get('days_since_last_treatment')
        t_washout = trial_data['temporal'].get('chemo_washout')
        
        if p_washout is not None and t_washout is not None:
            if p_washout >= t_washout:
                score += 5
                reasons.append(f"Washout Cleared: {p_washout}d > {t_washout}d")
            else:
                is_feasible = False 
                reasons.append(f"Washout Fail: Only {p_washout} days (Needs {t_washout})")

        # 8. LINES OF THERAPY
        p_lines = patient_profile.get('prior_lines')
        lines_rule = trial_data['lines_of_therapy']
        
        if p_lines is not None:
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
        
        if score < 40:
            is_feasible = False
            if not any("Condition Mismatch" in r for r in reasons):
                reasons.append("Low Relevance: No Condition or Biomarker match found.")

        # If infeasible, force score to 0 so it drops to the bottom
        final_score = min(score, 100) if is_feasible else 0
        
        return {
            "score": final_score,
            "is_feasible": is_feasible,
            "reasons": reasons,
            "parsed_criteria": trial_data
        }