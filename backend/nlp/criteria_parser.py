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
            "biomarkers": self._extract_biomarkers(text_lower)
        }

    def _extract_age(self, text):
        min_age = 0
        max_age = 100

        # Regex: (at least/age) + number + (optional space) + (years/yrs/yo)
        min_match = re.search(r"(?:≥|>=|at least|age|>\s*)\s*:?\s*(\d{1,3})\s*(?:years|yrs|y\.o\.|yo)", text)
        
        # Regex: (up to/younger than) + number + (optional space) + (years/yrs/yo)
        max_match = re.search(r"(?:≤|<=|up to|younger than)\s*:?\s*(\d{1,3})\s*(?:years|yrs|y\.o\.|yo)", text)

        if min_match:
            try:
                min_age = int(min_match.group(1))
            except ValueError:
                pass
        
        if max_match:
            try:
                max_age = int(max_match.group(1))
            except ValueError:
                pass

        # Sanity Check
        if min_age > 120: min_age = 0
        if max_age > 120: max_age = 100
        if min_age > max_age:
            max_age = 100

        return [min_age, max_age]

    def _extract_gender(self, text):
        # FIX: Matches "women" OR "female", and "men" OR "male"
        # Uses \b to ensure word boundaries
        has_female = re.search(r"\b(women|female|females)\b", text)
        has_male = re.search(r"\b(men|male|males)\b", text)

        if has_female and not has_male:
            return "Female"
        if has_male and not has_female:
            return "Male"
            
        return "All"

    def _extract_conditions(self, text):
        found = []
        for condition, terms in self.synonyms.items():
            # Skip biomarkers (handled separately)
            if condition.endswith("_Gene") or condition.endswith("_Receptor") or condition.endswith("_Level"):
                continue
            
            for term in terms:
                # Word boundaries for conditions
                pattern = r"\b" + re.escape(term.lower()) + r"\b"
                if re.search(pattern, text):
                    found.append(condition)
                    break 
        return found

    def _extract_biomarkers(self, text):
        found = []
        # UPDATED: Full list of supported labs/biomarkers
        keys = [
            "EGFR_Gene", "HER2_Receptor", "ALK_Gene", "KRAS_Gene",
            "Creatinine_Level", "GFR_Level",
            "Bilirubin_Level", "AST_Level", "ALT_Level", "PSA_Level"
        ]
        
        for key in keys:
            terms = self.synonyms.get(key, [])
            for term in terms:
                # Word boundaries so "walking" != "ALK"
                pattern = r"\b" + re.escape(term.lower()) + r"\b"
                if re.search(pattern, text):
                    # Clean the name (remove suffixes)
                    clean_name = key.replace("_Gene", "").replace("_Receptor", "").replace("_Level", "")
                    found.append(clean_name)
                    break
        return found
    