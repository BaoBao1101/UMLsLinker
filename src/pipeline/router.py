"""O-SRE Router: NLP Thuần - Lemmatization & Ontology Scoring (Enterprise Grade)."""
from __future__ import annotations

import logging
import re
import sqlite3
from typing import Dict, List, Any

import spacy

logger = logging.getLogger(__name__)

BOXES = [
    "chief_complaint", "subjective_symptoms", "past_medical_history",
    "objective_exam", "paraclinical", "diagnosis", "treatment",
    "lifestyle_advice", "other"
]

#Regex biên giới từ, không bao giờ bắt nhầm "no" trong 1 từ dài như "nodule" hoặc "notable". Cũng bao gồm các từ phủ định phổ biến khác trong y văn.
NEGATION_REGEX = re.compile(r"\b(deny|denies|no|not|without|rules? out|free of)\b", re.IGNORECASE)

HEADERS_REGEX = {
    r"(?i)\b(assessment|diagnosis)\b\s*:": "diagnosis",
    r"(?i)\b(plan|medications|treatment)\b\s*:": "treatment",
    r"(?i)\b(history of past illness|past medical history|past history)\b\s*:": "past_medical_history",
    r"(?i)\b(history of present illness|history)\b\s*:": "subjective_symptoms",
    r"(?i)\b(chief complaints?)\b\s*:": "chief_complaint",
    r"(?i)\b(physical examination|neurological examination|exam)\b\s*:": "objective_exam",
    r"(?i)\b(imaging examinations|laboratory examinations|imaging|labs|laboratory)\b\s*:": "paraclinical"
}

# TỪ ĐIỂN NGUYÊN THỂ LEMMA HEURISTICS: Dựa trên lemmatization để gán điểm cho từng box. Có thể mở rộng bằng cách thêm nhiều lemma hơn hoặc dùng model ML để học trọng số.
LEMMA_HEURISTICS = {
    "past_medical_history": {"history", "past", "previous", "childhood", "allergy", "habit"},
    "treatment": {"excision", "excise", "resection", "resect", "surgery", "prescribe", "sacrifice", "postoperative", "treat", "remove", "therapy", "dose", "medication", "administer"},
    "paraclinical": {"stain", "scan", "mri", "tomography", "histologic", "biopsy", "monitor", "potential", "atypia", "macroscopically", "microscopically", "evaluate", "reveal", "test", "assay", "culture", "x-ray", "ultrasound"},
    "subjective_symptoms": {"present", "complain", "symptom", "pain", "duration", "old", "year", "ache", "weakness", "numbness"},
    "diagnosis": {"diagnose", "diagnosis", "consistent", "finding", "malformation", "syndrome", "disease", "disorder", "carcinoma"}
}

ALLOWED_2_LETTER_ACRONYMS = {"ct", "mr", "xr", "pr", "er", "rf", "bp", "hr"}

class CascadingRouter:
    def __init__(self, db_path: str = "data/processed/open_umls.db", spacy_model: str = "en_core_sci_sm"):
        self.db_path = db_path
        try:
            self.nlp = spacy.load(spacy_model, disable=["ner"]) 
        except Exception:
            logger.warning("Vui lòng cài đặt: pip install en_core_sci_sm. Dùng tạm bản en_core_web_sm.")
            self.nlp = spacy.load("en_core_web_sm", disable=["ner"])

    def _get_fast_semantic_tags(self, clause: str) -> set:
        """Quét DB để lấy từ Ontology."""
        tags = set()
        # FIX: Cho phép từ >= 3 ký tự (như mass, cyst, cut) và các từ viết tắt y khoa 2 ký tự
        words = [w for w in re.split(r'\W+', clause.lower()) if len(w) >= 3 or w in ALLOWED_2_LETTER_ACRONYMS]
        if not words: return tags
        
        placeholders = ",".join("?" for _ in words)
        query = f"""
            SELECT semantic_type FROM concepts 
            WHERE canonical_name IN ({placeholders}) 
            OR cui IN (SELECT cui FROM synonyms WHERE term_string IN ({placeholders}))
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(query, words + words)
            for r in cur.fetchall():
                if r[0]: tags.add(r[0])
            conn.close()
        except: pass
        return tags

    def map_text_to_boxes(self, text: str) -> Dict[str, List[Dict[str, Any]]]:
        boxes_dict = {b: [] for b in BOXES}
        doc = self.nlp(text)
        current_header_zone = "other"
        
        for sent in doc.sents:
            clause = sent.text.strip()
            if not clause: continue
                
            # Dọn rác
            clause = re.sub(r'(?i)\[?(figure|fig\.|table|tab\.)\s*\d*[a-z]?\]?', '', clause).strip()
            if not clause: continue

            # 1. HEADER
            for pattern, h_box in HEADERS_REGEX.items():
                if re.search(pattern, clause):
                    current_header_zone = h_box
                    clause = re.sub(pattern, "", clause).strip()
                    break 
            
            if not clause: continue 

            clause_doc = self.nlp(clause)
            lemmas = {token.lemma_.lower() for token in clause_doc if not token.is_punct}
            lemmatized_string = " ".join(lemmas)

            has_patient = any(k in lemmas for k in {"patient", "male", "female", "he", "she", "case", "year", "boy", "girl", "man", "woman"})
            is_general_literature = any(k in lemmatized_string for k in {"report in literature", "comprise", "mostly locate", "rare condition", "remain controversial"})
            
            if is_general_literature and not has_patient:
                boxes_dict["other"].append({"text": clause})
                continue

            # TẦNG 0: Lọc Phủ Định dùng Regex
            is_negated = bool(NEGATION_REGEX.search(clause))
            if is_negated and "atypia" not in lemmas and "stain" not in lemmas:
                boxes_dict["other"].append({"text": clause})
                continue

            # THUẬT TOÁN ĐỊNH TUYẾN TRỌNG SỐ (WEIGHTED SCORING)
            box_scores = {b: 0.0 for b in BOXES}

            if current_header_zone != "other":
                box_scores[current_header_zone] += 4.0

            for box, keywords in LEMMA_HEURISTICS.items():
                intersection = lemmas.intersection(keywords)
                if intersection:
                    box_scores[box] += 3.0 + (0.5 * (len(intersection) - 1))

            tags = self._get_fast_semantic_tags(clause)
            if "T_PARACLINICAL" in tags: box_scores["paraclinical"] += 1.5
            if "T_TREATMENT" in tags or "T_DRUG" in tags: box_scores["treatment"] += 1.5
            if "T_DISEASE" in tags: box_scores["diagnosis"] += 1.5
            if "T_SYMPTOM" in tags: box_scores["subjective_symptoms"] += 1.5

            max_score = max(box_scores.values())

            if max_score < 1.0:
                boxes_dict["other"].append({"text": clause})
            else:
                best_boxes = []
                for box, score in box_scores.items():
                    if score >= max_score - 0.5 and score > 0:
                        best_boxes.append(box)

                if len(best_boxes) > 1 and "other" in best_boxes:
                    best_boxes.remove("other")

                for box in best_boxes:
                    boxes_dict[box].append({"text": clause})

        return boxes_dict