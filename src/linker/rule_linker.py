"""Rule-based linker: Exact and N-gram matching (Enterprise Version)."""
from __future__ import annotations

import logging
import re
import sqlite3
from collections import defaultdict
from typing import Dict, List, Optional

import spacy

logger = logging.getLogger(__name__)

PUNCT_RE = re.compile(r"[\W_]+")
SPACE_RE = re.compile(r"\s+")

def _normalize_term(s: Optional[str]) -> str:
    if not s: return ""
    s = str(s).strip().lower()
    s = PUNCT_RE.sub(" ", s)
    return SPACE_RE.sub(" ", s).strip()

class RuleLinker:
    def __init__(self, db_path: str = "data/processed/open_umls.db", spacy_model: str = "en_core_sci_sm"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.mapping: Dict[str, List[Dict]] = defaultdict(list)
        self.max_token_len = 1

        try:
            self.nlp = spacy.load(spacy_model, disable=["parser", "ner", "lemmatizer", "tagger"])
        except Exception:
            self.nlp = spacy.blank("en")

        self._setup_clinical_filters()
        self._load_synonyms_from_db()

    def _setup_clinical_filters(self) -> None:
        self.STOP_WORDS = {
            "was", "were", "is", "are", "has", "had", "have", "been", "be", "did", "do", "does",
            "also", "may", "can", "could", "would", "should", "using", "used", "which", "that",
            "figure", "table", "column", "image", "arrowhead", "case", "report", "literature",
            "left", "right", "all", "history", "patients", "patient", "macroscopically", "microscopically",
            "male", "female", "grade", "complete", "past", "present", "interest", "showed", "show",
            "blood", "hospital", "hospitals", "injury", "disease", "findings", "finding",
            "medicine", "surgery", "test", "tests", "pain", "severe", "course", "alone",
            "mild", "normal", "abnormal", "positive", "negative", "mass", "tissue", "cell", "cells",
            "low", "high", "none", "without", "with", "due", "from", "total", "about",
            "years", "days", "months", "weeks", "old", "year", "rate", "duration", "time"
        }
        
        self.ALLOWED_SHORT_WORDS = {
            "ct", "mr", "er", "mg", "iv", "po", "bp", "hr", "rf", "tg", "psa", "ema", "erg", "us", "xr", "pr",
            "l1", "l2", "l3", "l4", "l5", "s1", "s2", 
            "c1", "c2", "c3", "c4", "c5", "c6", "c7",
            "t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9", "t10", "t11", "t12"
        }

    def _is_valid_clinical_term(self, norm_text: str) -> bool:
        if not norm_text or norm_text.isdigit(): return False
        if re.search(r'(?i)figure\s*\d*|table\s*\d*|column|image\s*[a-z]?', norm_text): return False
        if len(norm_text) <= 2 and norm_text not in self.ALLOWED_SHORT_WORDS: return False
        if norm_text in self.STOP_WORDS: return False
        return True

    def _load_synonyms_from_db(self) -> None:
        q = "SELECT s.sui, s.cui, s.term_string, c.canonical_name, c.source_ontology, c.semantic_type FROM synonyms s JOIN concepts c ON s.cui = c.cui"
        try:
            cur = self.conn.cursor()
            rows = cur.execute(q).fetchall()
        except Exception as exc:
            logger.error("Failed to query DB %s: %s", self.db_path, exc)
            rows = []

        for sui, cui, term_string, canonical_name, source_ontology, semantic_type in rows:
            norm = _normalize_term(term_string)
            if not self._is_valid_clinical_term(norm): continue
            self.mapping[norm].append({
                "sui": sui, "cui": cui, "term_string": term_string,
                "canonical_name": canonical_name, "source_ontology": source_ontology,
                "semantic_type": semantic_type,
            })

        if self.mapping:
            self.max_token_len = max(len(k.split()) for k in self.mapping.keys())
        else:
            self.max_token_len = 1

    def match_text(self, text: str, max_results_per_span: int = 5) -> List[Dict]:
        doc = self.nlp(text)
        tokens = [t.text for t in doc]
        n_tokens = len(tokens)
        matches: List[Dict] = []
        i = 0
        
        while i < n_tokens:
            matched = False
            max_w = min(self.max_token_len, n_tokens - i)
            for L in range(max_w, 0, -1):
                span_tokens = tokens[i : i + L]
                candidate = " ".join(span_tokens)
                
                # Bỏ qua cụm từ nằm trong ngoặc (có thể sử đổi để chỉ bỏ qua ngoặc vuông)
                if re.search(r'\[.*\]|\(.*\)', candidate):
                    continue

                norm_candidate = _normalize_term(candidate)
                if not norm_candidate: continue
                    
                if norm_candidate in self.mapping:
                    entries = self.mapping[norm_candidate]
                    start_char = doc[i].idx
                    end_char = doc[i + L - 1].idx + len(doc[i + L - 1].text)
                    for entry in entries[:max_results_per_span]:
                        matches.append({
                            "sui": entry["sui"], "cui": entry["cui"],
                            "term_string": entry["term_string"], "canonical_name": entry["canonical_name"],
                            "source_ontology": entry["source_ontology"], "semantic_type": entry["semantic_type"],
                            "start_char": start_char, "end_char": end_char,
                            "score": 1.0, "match_type": "rule", "matched_text": candidate,
                        })
                    matched = True
                    i += L
                    break
            if not matched:
                i += 1

        seen = set()
        deduped: List[Dict] = []
        for m in matches:
            key = (m["cui"], m["start_char"], m["end_char"])
            if key in seen: continue
            seen.add(key)
            deduped.append(m)

        return deduped