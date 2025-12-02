import spacy
import scispacy
from scispacy.linking import EntityLinker
from typing import Set, List, Tuple
import logging

logger = logging.getLogger(__name__)

class UMLSLinker:
    _instance = None
    _nlp = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UMLSLinker, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        logger.info("Loading scispacy model 'en_core_sci_sm'...")
        try:
            self._nlp = spacy.load("en_core_sci_sm")
            # We add the linker to the pipeline. 
            # Note: 'umls' linker requires internet to download the KB first time, or pre-downloaded.
            # For this prototype, we'll use the 'umls' linker provided by scispacy.
            # Warning: The full UMLS linker is heavy. We might want to use a lighter approach or just entity detection 
            # if the full linker is too slow/large for this environment.
            # Let's try to add it. If it fails, we fallback to just canonical entity text.
            
            # For the purpose of this "hardcore" request, we will try to use the linker.
            # However, the default 'umls' linker in scispacy downloads ~1GB. 
            # To avoid blocking for too long, we will use the 'canonical_name' from the entity itself 
            # as a proxy for CUI if the linker isn't feasible, but let's try to do it right.
            
            # Actually, for a quick prototype without massive downloads, we can rely on 
            # the scispacy entity detection which is already very good at normalizing.
            # But the user specifically asked for "Concept IDs (CUIs)".
            # The 'umls' linker is the standard way.
            
            self._nlp.add_pipe("scispacy_linker", config={"resolve_abbreviations": True, "linker_name": "umls"})
            logger.info("UMLS Linker loaded successfully.")
        except Exception as e:
            logger.warning(f"Failed to load UMLS linker: {e}. Fallback to entity text only.")
            # Fallback: just load the model without the linker step if it fails (e.g. memory/network)
            if not self._nlp:
                self._nlp = spacy.load("en_core_sci_sm")

    def extract_cuis(self, text: str) -> Set[str]:
        """
        Extracts UMLS Concept Unique Identifiers (CUIs) from the text.
        Returns a set of CUI strings (e.g., {'C0027051', 'C0011849'}).
        """
        if not text:
            return set()
            
        doc = self._nlp(text)
        cuis = set()
        
        try:
            linker = self._nlp.get_pipe("scispacy_linker")
            for ent in doc.ents:
                for umls_ent in ent._.kb_ents:
                    # umls_ent is (cui, score)
                    # We only take high confidence matches? Or just the top one?
                    # Let's take the top one for each entity.
                    cuis.add(umls_ent[0])
        except KeyError:
            # Linker not in pipeline
            pass
            
        return cuis

    def extract_entities(self, text: str) -> Set[str]:
        """
        Returns canonical names of entities if CUI linking fails.
        """
        if not text:
            return set()
        doc = self._nlp(text)
        return {ent.text.lower() for ent in doc.ents}
