"""Combined core engine for the O-SRE Medical Extraction Pipeline (Enterprise Grade)."""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Any

from .rule_linker import RuleLinker
from .neural_linker import NeuralLinker
from ..pipeline.router import CascadingRouter

logger = logging.getLogger(__name__)

class OpenUMLSEngine:
    def __init__(self, db_path: str = "data/processed/open_umls.db", spacy_model: str = "en_core_web_sm"):
        self.db_path = db_path
        self.router = CascadingRouter(spacy_model=spacy_model)
        self.rule = RuleLinker(db_path=self.db_path, spacy_model=spacy_model)
        self.neural = NeuralLinker(db_path=self.db_path)

    def map_document(self, text: str, top_k: int = 5, neural_threshold: float = 0.85) -> Dict[str, List[Dict[str, Any]]]:
        boxes = self.router.map_text_to_boxes(text)
        output: Dict[str, List[Dict[str, Any]]] = {}

        for box, clauses in boxes.items():
            out_list: List[Dict[str, Any]] = []
            for clause_obj in clauses:
                clause_text = clause_obj.get("text", "").strip()
                

                if not clause_text or re.fullmatch(r'[\W\d_]+', clause_text) or len(clause_text.split()) < 2:
                    continue

                candidates = []
                seen_cuis = set() # CHỐNG TRÙNG LẶP CUI GIỮA RULE VÀ NEURAL

                # 1. Rule matches
                rule_matches = self.rule.match_text(clause_text, max_results_per_span=top_k)
                if rule_matches:
                    for m in rule_matches:
                        candidates.append({
                            "cui": m["cui"],
                            "canonical_name": m.get("canonical_name"),
                            "source_ontology": m.get("source_ontology"),
                            "semantic_type": m.get("semantic_type"),
                            "score": m.get("score", 1.0),
                            "match_type": "rule",
                        })
                        seen_cuis.add(m["cui"])
                else:
                    # 2. Neural matches (Chỉ chạy khi Rule k tìm thấy j)
                    try:
                        nn = self.neural.search(clause_text, top_k=top_k, score_threshold=neural_threshold)
                        for r in nn:
                            # Không add trùng CUI đã có
                            if r.get("cui") not in seen_cuis:
                                candidates.append({
                                    "cui": r.get("cui"),
                                    "term_string": r.get("term_string"),
                                    "canonical_name": r.get("canonical_name"),
                                    "semantic_type": r.get("semantic_type"),
                                    "score": r.get("score"),
                                    "match_type": "neural",
                                })
                                seen_cuis.add(r.get("cui"))
                    except Exception as exc:
                        logger.warning("Neural search failed for '%s': %s", clause_text, exc)

                if candidates:
                    out_list.append({"text": clause_text, "candidates": candidates})
            
            output[box] = out_list

        return output