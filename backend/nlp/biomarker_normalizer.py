# backend/nlp/biomarker_normalizer.py

import json
import os
import re
from typing import List, Optional


SUFFIXES = [
    "_Gene", "_Receptor", "_Marker", "_Status", "_Mutation", "_Score", "_Level", "_Count"
]


class BiomarkerNormalizer:
    """

    Examples:
      - "L858R"           -> "EGFR"
      - "BRAF V600E"      -> "BRAF"
      - "MET exon 14"     -> "MET"
      - "PD-L1"           -> "PD_L1_Expression" (cleaned remains the same key minus suffixes)
      - "MSI-H"           -> "MSI"
    """

    def __init__(self, synonym_file: str = "clinical_synonyms.json") -> None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, synonym_file)
        try:
            with open(file_path, "r") as f:
                self.synonyms = json.load(f)
        except FileNotFoundError:
            print(f"Error: Could not find {file_path}")
            self.synonyms = {}

        
        self.reverse_lookup = {}
        for key, terms in self.synonyms.items():
            if not any(suf in key for suf in SUFFIXES):
                continue
            clean = self._clean_name(key)
            for term in terms:
                t = term.lower().strip()
                if t:
                    self.reverse_lookup[t] = clean

    def _clean_name(self, key: str) -> str:
        clean = key
        for suf in SUFFIXES:
            clean = clean.replace(suf, "")
        return clean

    def normalize(self, biomarker_text: str) -> Optional[str]:
        if not biomarker_text:
            return None
        text = biomarker_text.lower().strip()

        # exact synonym match
        if text in self.reverse_lookup:
            return self.reverse_lookup[text]

        # partial containment (handles variants like "V600E", "L858R", "exon 14")
        for syn, clean in self.reverse_lookup.items():
            pattern = r"\\b" + re.escape(syn) + r"\\b"
            if re.search(pattern, text):
                return clean

        # reverse containment
        for syn, clean in self.reverse_lookup.items():
            pattern = r"\\b" + re.escape(text) + r"\\b"
            if re.search(pattern, syn):
                return clean

        return None

    def normalize_list(self, biomarkers: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for b in biomarkers or []:
            norm = self.normalize(b)
            if norm and norm not in seen:
                out.append(norm)
                seen.add(norm)
        return out


# Singleton 
_b_normalizer = None


def get_biomarker_normalizer() -> BiomarkerNormalizer:
    global _b_normalizer
    if _b_normalizer is None:
        _b_normalizer = BiomarkerNormalizer()
    return _b_normalizer
