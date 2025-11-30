# backend/nlp/condition_normalizer.py

import json
import os
import re
from typing import List, Optional


class ConditionNormalizer:

    def __init__(self, synonym_file="clinical_synonyms.json"):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, synonym_file)
        
        try:
            with open(file_path, "r") as f:
                self.synonyms = json.load(f)
        except FileNotFoundError:
            print(f"Error: Could not find {file_path}")
            self.synonyms = {}
        
        # Build reverse lookup
        # Only include disease conditions (exclude biomarkers)
        self.reverse_lookup = {}
        for key, terms in self.synonyms.items():
            # Skip biomarker keys
            if any(suffix in key for suffix in ["_Gene", "_Receptor", "_Status", "_Marker", "_Level", "_Count", "_Mutation", "_Score"]):
                continue
            
            # Map each synonym to the normalized key
            for term in terms:
                normalized_term = term.lower().strip()
                self.reverse_lookup[normalized_term] = key
    
    def normalize(self, condition_text: str) -> Optional[str]:
        normalized_input = condition_text.lower().strip()
        
        # Exact match
        if normalized_input in self.reverse_lookup:
            return self.reverse_lookup[normalized_input]
        
        # Partial match: 
        # This handles cases like "metastatic thyroid cancer" to "Thyroid_Cancer"
        for synonym, key in self.reverse_lookup.items():
            # Match whole words to avoid false positives
            pattern = r'\b' + re.escape(synonym) + r'\b'
            if re.search(pattern, normalized_input):
                return key
        
        # Reverse: Check if any synonym contains the input
        # Handles "thyroid cancer" matching "Papillary Thyroid Cancer"
        for synonym, key in self.reverse_lookup.items():
            pattern = r'\b' + re.escape(normalized_input) + r'\b'
            if re.search(pattern, synonym):
                return key
        
        return None
    
    def normalize_list(self, conditions: List[str]) -> List[str]:
        normalized = []
        seen = set()
        
        for condition in conditions:
            key = self.normalize(condition)
            if key and key not in seen:
                normalized.append(key)
                seen.add(key)
        
        return normalized
    
    def get_all_synonyms(self, normalized_key: str) -> List[str]:
        return self.synonyms.get(normalized_key, [])


# Singleton instance
_normalizer = None

def get_condition_normalizer() -> ConditionNormalizer:
    """Get singleton instance of ConditionNormalizer."""
    global _normalizer
    if _normalizer is None:
        _normalizer = ConditionNormalizer()
    return _normalizer
