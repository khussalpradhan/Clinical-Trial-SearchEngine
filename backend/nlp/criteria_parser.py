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
            "ecog": self._extract_ecog(text_lower)  # <--- NEW FIELD [K-202]
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
        # Matches "women" OR "female", and "men" OR "male"
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
        # Full list of supported labs/biomarkers
        keys = [
            "EGFR_Gene", "HER2_Receptor", "ALK_Gene", "KRAS_Gene",
            "Creatinine_Level", "GFR_Level",
            "Bilirubin_Level", "AST_Level", "ALT_Level", "PSA_Level"
        ]
        
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
        """
        Extracts allowed ECOG/WHO/Zubrod scores. 
        Returns a list of allowed integers, e.g., [0, 1].
        """
        allowed_scores = set()
        
        # 1. Ranges: "ECOG 0-1", "ECOG 0 to 2", "Zubrod 0-1"
        range_match = re.search(r"(?:ecog|zubrod|who).*?status.*?(\d)\s*(?:-|to)\s*(\d)", text)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if start <= end and end <= 5:
                for i in range(start, end + 1):
                    allowed_scores.add(i)
        
        # 2. Inequalities: "ECOG <= 2", "ECOG < 2"
        lte_match = re.search(r"(?:ecog|zubrod|who).*?(?:≤|<=|up to|less than).*?(\d)", text)
        if lte_match:
            limit = int(lte_match.group(1))
            if limit <= 5:
                for i in range(0, limit + 1):
                    allowed_scores.add(i)

        # 3. Explicit Lists: "ECOG 0 or 1"
        if not allowed_scores:
            simple_match = re.search(r"(?:ecog|zubrod|who).*?(\d)(?:\s*or\s*|\s*,\s*)(\d)", text)
            if simple_match:
                allowed_scores.add(int(simple_match.group(1)))
                allowed_scores.add(int(simple_match.group(2)))

        return sorted(list(allowed_scores))