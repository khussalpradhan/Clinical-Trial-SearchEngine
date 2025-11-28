import re
import json
import os

try:
    import spacy
except ImportError:
    spacy = None

class CriteriaParser:
    def __init__(self, synonym_file="clinical_synonyms.json"):
        # 1. Load the dictionary
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, synonym_file)

        try:
            with open(file_path, "r") as f:
                self.synonyms = json.load(f)
        except FileNotFoundError:
            print(f"Error: Could not find {file_path}")
            self.synonyms = {}

        # 2. Load spaCy model if available
        if spacy:
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except Exception:
                self.nlp = None
        else:
            self.nlp = None

    def parse(self, criteria_text):
        if not criteria_text:
            return {}

        text_lower = criteria_text.lower()

        return {
            "age_range": self._extract_age(text_lower),
            "gender": self._extract_gender(text_lower),
            "conditions": self._extract_conditions(text_lower),
            "biomarkers": self._extract_biomarkers(text_lower),
            "ecog": self._extract_ecog(text_lower),
            "labs": self._extract_labs(text_lower) 
        }

    def _extract_age(self, text):
        min_age = 0
        max_age = 100
        min_match = re.search(r"(?:≥|>=|at least|age|>\s*)\s*:?\s*(\d{1,3})\s*(?:years|yrs|y\.o\.|yo)", text)
        max_match = re.search(r"(?:≤|<=|up to|younger than)\s*:?\s*(\d{1,3})\s*(?:years|yrs|y\.o\.|yo)", text)
        if min_match:
            try: min_age = int(min_match.group(1))
            except ValueError: pass
        if max_match:
            try: max_age = int(max_match.group(1))
            except ValueError: pass
        if min_age > 120: min_age = 0
        if max_age > 120: max_age = 100
        if min_age > max_age: max_age = 100
        return [min_age, max_age]

    def _extract_gender(self, text):
        has_female = re.search(r"\b(women|female|females)\b", text)
        has_male = re.search(r"\b(men|male|males)\b", text)
        if has_female and not has_male: return "Female"
        if has_male and not has_female: return "Male"
        return "All"

    def _extract_conditions(self, text):
        found = []
        for condition, terms in self.synonyms.items():
            if condition.endswith("_Gene") or condition.endswith("_Receptor") or condition.endswith("_Level"): continue
            for term in terms:
                pattern = r"\b" + re.escape(term.lower()) + r"\b"
                if re.search(pattern, text):
                    found.append(condition)
                    break 
        return found

    def _extract_biomarkers(self, text):
        found = []
        keys = ["EGFR_Gene", "HER2_Receptor", "ALK_Gene", "KRAS_Gene", "Creatinine_Level", "GFR_Level", "Bilirubin_Level", "AST_Level", "ALT_Level", "PSA_Level"]
        for key in keys:
            terms = self.synonyms.get(key, [])
            for term in terms:
                pattern = r"\b" + re.escape(term.lower()) + r"\b"
                if re.search(pattern, text):
                    clean_name = key.replace("_Gene", "").replace("_Receptor", "").replace("_Level", "")
                    found.append(clean_name)
                    break
        return found

    def _extract_ecog(self, text):
        allowed_scores = set()
        range_match = re.search(r"(?:ecog|zubrod|who).*?status.*?(\d)\s*(?:-|to)\s*(\d)", text)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            if start <= end and end <= 5:
                for i in range(start, end + 1): allowed_scores.add(i)
        lte_match = re.search(r"(?:ecog|zubrod|who).*?(?:≤|<=|up to|less than).*?(\d)", text)
        if lte_match:
            limit = int(lte_match.group(1))
            if limit <= 5:
                for i in range(0, limit + 1): allowed_scores.add(i)
        if not allowed_scores:
            simple_match = re.search(r"(?:ecog|zubrod|who).*?(\d)(?:\s*or\s*|\s*,\s*)(\d)", text)
            if simple_match:
                allowed_scores.add(int(simple_match.group(1)))
                allowed_scores.add(int(simple_match.group(2)))
        return sorted(list(allowed_scores))

    def _extract_labs(self, text):
        """
        Extracts lab thresholds (e.g., 'Creatinine > 1.5').
        Returns: { 'Creatinine': { 'operator': '>', 'value': 1.5, 'unit': 'mg/dl' }, ... }
        """
        labs_found = {}
        
        # 1. Define the targets we care about (must match keys in synonyms json)
        lab_targets = ["Creatinine_Level", "GFR_Level", "Bilirubin_Level", "AST_Level", "ALT_Level", "PSA_Level"]
        
        # 2. Define the regex for operators and values
        # Matches: >, <, >=, <=, =, "greater than", "less than"
        # Followed by a number (integer or decimal)
        # Followed optionally by units
        op_pattern = r"(>|>=|<|<=|≥|≤|greater than|less than|equals|up to)\s*(\d+(?:\.\d+)?)\s*([a-z/]+)?"
        
        for lab_key in lab_targets:
            # Get all synonyms for this lab (e.g., "SCr", "Creatinine")
            terms = self.synonyms.get(lab_key, [])
            clean_name = lab_key.replace("_Level", "")
            
            for term in terms:
                # Look for: "Creatinine ... > ... 1.5"
                # We allow up to 20 characters between the name and the operator (to skip words like "level of")
                full_pattern = r"\b" + re.escape(term.lower()) + r"\b.{0,20}?" + op_pattern
                
                match = re.search(full_pattern, text)
                if match:
                    raw_op = match.group(1)
                    value = float(match.group(2))
                    unit = match.group(3) if match.group(3) else ""
                    
                    # Normalize operator
                    op = raw_op
                    if "greater" in raw_op or ">" in raw_op or "≥" in raw_op: op = ">"
                    elif "less" in raw_op or "<" in raw_op or "≤" in raw_op or "up to" in raw_op: op = "<"
                    
                    labs_found[clean_name] = {
                        "operator": op,
                        "value": value,
                        "unit": unit.strip()
                    }
                    break # Found one rule for this lab, stop looking
                    
        return labs_found