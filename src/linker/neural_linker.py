"""Neural linker with SapBERT (Enterprise Version)."""
from __future__ import annotations

import logging
import os
import sqlite3
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

class NeuralLinker:
    def __init__(
        self,
        db_path: str = "data/processed/open_umls.db",
        index_dir: str = "data/processed/vector_index",
        model_name: str = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext",
        device: str = "cpu",
        use_faiss: bool = False,
    ) -> None:
        self.db_path = db_path
        self.index_dir = index_dir
        self.parts_dir = os.path.join(self.index_dir, "parts")
        self.model_name = model_name
        self.device = device
        self.use_faiss = use_faiss

        self._model = None
        self._meta: Optional[pd.DataFrame] = None
        self._vectors: Optional[np.ndarray] = None
        self._faiss_index = None
        self._dim: Optional[int] = None

    def _lazy_load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name, device=self.device)
                self._dim = self._model.get_sentence_embedding_dimension()
                logger.info("Loaded embedding model %s (dim=%d)", self.model_name, self._dim)
            except ImportError:
                raise ImportError("Please install sentence-transformers.")

    def load_index(self) -> None:
        v_path = os.path.join(self.index_dir, "merged_vectors.npy")
        m_path = os.path.join(self.index_dir, "merged_meta.parquet")
        if not os.path.exists(v_path) or not os.path.exists(m_path):
            raise FileNotFoundError("Index not found. Please build_index() first.")

        self._vectors = np.load(v_path)
        self._meta = pd.read_parquet(m_path)
        logger.info("NeuralLinker loaded %d vectors from %s", len(self._vectors), self.index_dir)

    def _search_numpy(self, q_emb: np.ndarray, top_k: int = 5) -> List[Tuple[int, float]]:
        scores = np.dot(self._vectors, q_emb)
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(int(idx), float(scores[idx])) for idx in top_indices]

    def search(self, text: str, top_k: int = 5, score_threshold: float = 0.85) -> List[dict]:
        if self._model is None:
            self._lazy_load_model()
            
        if len(text.strip()) <= 2:
            return []

        q_emb = self._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        if self._vectors is None:
            self.load_index()
            
        neighbors = self._search_numpy(q_emb, top_k=top_k)
        results = []
        
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        for idx, score in neighbors:
            if float(score) < score_threshold:
                continue

            meta = self._meta.iloc[idx].to_dict() if self._meta is not None else {}
            cui_val = meta.get("cui")
            
            sem_type_val = None
            canonical_val = ""
            if cui_val:
                cur.execute("SELECT semantic_type, canonical_name FROM concepts WHERE cui = ? LIMIT 1", (cui_val,))
                row = cur.fetchone()
                if row:
                    sem_type_val = row[0]
                    canonical_val = row[1]

            results.append({
                "sui": meta.get("sui"), 
                "cui": cui_val, 
                "term_string": meta.get("term_string"), 
                "canonical_name": canonical_val,
                "semantic_type": sem_type_val,
                "score": float(score),
                "match_type": "neural"
            })
            
        conn.close()
        return results