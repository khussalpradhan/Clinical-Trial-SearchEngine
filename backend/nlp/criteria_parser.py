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

        # FIX 1: Look for "years", "yrs", "yo" to avoid lab values like "125 lbs"
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

        # FIX 2: Sanity Check - Humans rarely live past 120, and Min shouldn't be > Max
        if min_age > 120: min_age = 0
        if max_age > 120: max_age = 100
        
        if min_age > max_age:
            # If we parsed [18, 10], something is wrong. Trust the Min (18) and reset Max.
            max_age = 100

        return [min_age, max_age]

    def _extract_gender(self, text):
        # FIX 3: Word boundaries (\b) to prevent "supplement" matching "men"
        has_women = re.search(r"\bwomen\b", text)
        has_men = re.search(r"\bmen\b", text)

        if has_women and not has_men:
            return "Female"
        if has_men and not has_women:
            return "Male"
        return "All"

    def _extract_conditions(self, text):
        found = []
        for condition, terms in self.synonyms.items():
            if condition.endswith("_Gene") or condition.endswith("_Receptor"):
                continue
            
            for term in terms:
                # FIX 3: Word boundaries for conditions
                pattern = r"\b" + re.escape(term.lower()) + r"\b"
                if re.search(pattern, text):
                    found.append(condition)
                    break 
        return found

    def _extract_biomarkers(self, text):
        found = []
        keys = ["EGFR_Gene", "HER2_Receptor", "ALK_Gene", "KRAS_Gene"]
        for key in keys:
            terms = self.synonyms.get(key, [])
            for term in terms:
                # FIX 3: Word boundaries so "walking" != "ALK"
                pattern = r"\b" + re.escape(term.lower()) + r"\b"
                if re.search(pattern, text):
                    clean_name = key.replace("_Gene", "").replace("_Receptor", "")
                    found.append(clean_name)
                    break
        return found