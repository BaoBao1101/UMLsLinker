"""Simple 4-tier cascading router that maps atomic clauses into 9 JSON boxes.

This is a lightweight, rule-driven router intended as a starting point. It
uses spaCy to split text into clauses/sentences and simple keyword-based
heuristics to map each clause into one of the boxes:

  administrative, hpi, past_history, subjective_symptoms, objective_exam,
  paraclinical, diagnosis, treatment, red_flags

The heuristics are intentionally simple so the component can be replaced
later with model-based classifiers while preserving the I/O contract.
"""
from __future__ import annotations

import logging
from typing import Dict, List

import spacy

logger = logging.getLogger(__name__)


DEFAULT_KEYWORDS = {
    "administrative": ["mr.", "mrs.", "patient id", "admitted", "discharged", "dob", "age"],
    "hpi": ["presenting", "history of present", "presents with", "complaint", "onset"],
    "past_history": ["history of", "hx of", "past history", "previously"],
    "subjective_symptoms": ["pain", "feels", "reports", "denies", "nausea", "headache", "cough"],
    "objective_exam": ["on exam", "blood pressure", "heart rate", "equals", "mmhg", "auscultation", "palpation"],
    "paraclinical": ["lab", "imaging", "x-ray", "ecg", "ct", "mri", "ultrasound", "cbc", "bmp"],
    "diagnosis": ["diagnosis", "dx", "likely", "suspected", "rule out", "ruled out"],
    "treatment": ["treat", "prescribe", "administer", "start", "stop", "surgery", "give", "dose", "mg"],
    "red_flags": ["severe", "sudden", "loss of consciousness", "bleeding", "acute", "difficulty breathing", "urgent", "life-threatening"],
}

BOX_ORDER = [
    "administrative",
    "hpi",
    "past_history",
    "subjective_symptoms",
    "objective_exam",
    "paraclinical",
    "diagnosis",
    "treatment",
    "red_flags",
]


class CascadingRouter:
    def __init__(self, spacy_model: str = "en_core_web_sm", keywords: Dict[str, List[str]] | None = None):
        try:
            self.nlp = spacy.load(spacy_model, disable=["parser", "tagger", "lemmatizer"])  # type: ignore
        except Exception:
            logger.warning("spaCy model '%s' not available; falling back to blank 'en'", spacy_model)
            self.nlp = spacy.blank("en")
        self.keywords = keywords or DEFAULT_KEYWORDS

    def _score_clause(self, clause: str) -> Dict[str, int]:
        low = clause.lower()
        scores = {k: 0 for k in self.keywords.keys()}
        for box, kws in self.keywords.items():
            for kw in kws:
                if kw in low:
                    scores[box] += 1
        return scores

    def route_clause(self, clause: str) -> str:
        scores = self._score_clause(clause)
        # Prefer red_flags if any matches (safety priority)
        if scores.get("red_flags", 0) > 0:
            return "red_flags"
        # Otherwise pick highest score; tie-break by BOX_ORDER
        best = None
        best_score = 0
        for box in BOX_ORDER:
            sc = scores.get(box, 0)
            if sc > best_score:
                best = box
                best_score = sc
        return best or "hpi"

    def map_text_to_boxes(self, text: str) -> Dict[str, List[Dict[str, str]]]:
        doc = self.nlp(text)
        # split into sentences as atomic clauses
        clauses = [sent.text.strip() for sent in getattr(doc, "sents", [])]
        if not clauses:
            # fallback: simple sentence split by punctuation
            clauses = [c.strip() for c in text.split(".") if c.strip()]

        boxes: Dict[str, List[Dict[str, str]]] = {b: [] for b in BOX_ORDER}
        for clause in clauses:
+            if not clause:
+                continue
+            box = self.route_clause(clause)
+            boxes.setdefault(box, []).append({"text": clause})
+
+        return boxes
+
+
+if __name__ == "__main__":
+    r = CascadingRouter()
+    example = (
+        "Mr. Smith, a 45-year-old male, presents with sudden severe chest pain. "
+        "On exam his blood pressure is 90/60 and he is diaphoretic. We ordered an ECG and troponin. "
+        "Plan to give aspirin and transfer to cath lab."
+    )
+    out = r.map_text_to_boxes(example)
+    import json
+
+    print(json.dumps(out, indent=2))
*** End Patch