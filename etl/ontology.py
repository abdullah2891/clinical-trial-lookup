"""
SNOMED/ICD-10 ontology mapping and UMLS concept enrichment.

Uses SciSpacy's en_core_sci_lg model for named entity recognition,
then links entities to UMLS CUIs via scispacy's EntityLinker.

Usage:
    mapper = OntologyMapper()
    entities = mapper.extract_entities("chest tightness and dyspnea")
    # → [UMLSEntity(cui="C0013404", name="Dyspnea", ...)]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_nlp = None  # lazy-loaded spacy model


def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            from scispacy.linking import EntityLinker  # noqa: F401

            _nlp = spacy.load("en_core_sci_lg")
            _nlp.add_pipe(
                "scispacy_linker",
                config={"resolve_abbreviations": True, "linker_name": "umls"},
            )
        except Exception as exc:
            logger.warning("SciSpacy model load failed: %s", exc)
            _nlp = None
    return _nlp


@dataclass
class UMLSEntity:
    text: str
    cui: str
    name: str
    score: float
    semantic_types: list[str]


class OntologyMapper:
    """Extracts UMLS entities from clinical text using SciSpacy."""

    def extract_entities(self, text: str) -> list[UMLSEntity]:
        nlp = _get_nlp()
        if nlp is None:
            return []

        try:
            doc = nlp(text)
            entities: list[UMLSEntity] = []
            linker = nlp.get_pipe("scispacy_linker")

            for ent in doc.ents:
                for kb_ent in ent._.kb_ents[:1]:  # top match only
                    cui, score = kb_ent
                    concept = linker.kb.cui_to_entity.get(cui)
                    if concept:
                        entities.append(
                            UMLSEntity(
                                text=ent.text,
                                cui=cui,
                                name=concept.canonical_name,
                                score=float(score),
                                semantic_types=list(concept.types),
                            )
                        )
            return entities
        except Exception as exc:
            logger.warning("Entity extraction failed: %s", exc)
            return []

    def extract_condition_names(self, text: str) -> list[str]:
        """Return canonical condition names from text (for search queries)."""
        entities = self.extract_entities(text)
        condition_types = {"T047", "T048", "T184", "T191"}  # disease/symptom types
        names = [
            e.name
            for e in entities
            if any(t in condition_types for t in e.semantic_types)
        ]
        return names or [text]  # fall back to raw text
