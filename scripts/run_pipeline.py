"""Run full ETL and optional vector index build.

Example:
    python scripts/run_pipeline.py --raw_dir data/raw --out data/processed/open_umls.db --build_index --index_batch_size 512
"""
from __future__ import annotations

import argparse
import logging
import os

from src.etl import build_database as bd
from src.linker.neural_linker import NeuralLinker

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw_dir", default="data/raw")
    p.add_argument("--out", default="data/processed/open_umls.db")
    p.add_argument("--out_dir", default="data/processed")
    p.add_argument("--chunk_size", type=int, default=2000)
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--no_csv", dest="write_csv", action="store_false")
    p.add_argument("--build_index", action="store_true")
    p.add_argument("--index_batch_size", type=int, default=512)
    p.add_argument("--index_dir", default="data/processed/vector_index")
    args = p.parse_args()

    mesh_path, ontology_paths = bd._find_default_files(args.raw_dir)
    logger.info("Starting ETL: mesh=%s, ontologies=%d", mesh_path, len(ontology_paths))
    bd.build_database(args.raw_dir, mesh_path, ontology_paths, args.out, out_dir=args.out_dir, chunk_size=args.chunk_size, overwrite=args.overwrite, write_csv=args.write_csv)

    if args.build_index:
        logger.info("Building vector index into %s (batch_size=%d)", args.index_dir, args.index_batch_size)
        nl = NeuralLinker(db_path=args.out, index_dir=args.index_dir)
        nl.build_index(batch_size=args.index_batch_size, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
