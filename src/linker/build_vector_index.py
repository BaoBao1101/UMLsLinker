"""Script to build a dense vector index for all synonyms.

This script calls `NeuralLinker.build_index` and persists the resulting
vectors and metadata under `data/processed/vector_index/`.

WARNING: This operation can be time-consuming and memory intensive. Run on
a machine with sufficient RAM and disk space.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/processed/open_umls.db")
    p.add_argument("--index_dir", default="data/processed/vector_index")
    p.add_argument("--batch_size", default=128, type=int)
    p.add_argument("--use_faiss", action="store_true")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()


    # ensure `src` is on PYTHONPATH so `import linker.*` works when running
    # this script from the repository root or from inside `src/linker`.
    repo_src = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo_src not in sys.path:
        sys.path.insert(0, repo_src)

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("build_vector_index")

    try:
        from linker.neural_linker import NeuralLinker
    except Exception as exc:
        logger.exception("Failed to import NeuralLinker: %s", exc)
        raise

    nl = NeuralLinker(db_path=args.db, index_dir=args.index_dir, use_faiss=args.use_faiss, device="cpu")

    try:
        nl.build_index(batch_size=args.batch_size, use_faiss=args.use_faiss, overwrite=args.overwrite)
        logger.info("Index build completed successfully")
    except Exception as exc:
        logger.exception("Index build failed: %s", exc)
        raise


if __name__ == "__main__":
    main()
