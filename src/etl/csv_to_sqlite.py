#!/usr/bin/env python3
"""Convert processed CSV outputs into a lightweight SQLite DB for the Engine.

Reads:
  - data/processed/concepts.csv
  - data/processed/synonyms.csv

Writes:
  - data/processed/open_umls.db with tables `concepts` and `synonyms`.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys

import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def csv_to_sqlite(processed_dir: str | None = None, out_db: str | None = None) -> None:
    processed_dir = processed_dir or os.path.join(os.getcwd(), "data", "processed")
    concepts_csv = os.path.join(processed_dir, "concepts.csv")
    synonyms_csv = os.path.join(processed_dir, "synonyms.csv")
    out_db = out_db or os.path.join(processed_dir, "open_umls.db")

    if not os.path.exists(processed_dir):
        logger.error("Processed directory not found: %s", processed_dir)
        raise SystemExit(2)

    if not os.path.exists(concepts_csv) or not os.path.exists(synonyms_csv):
        logger.error("Required CSVs missing in %s. Expecting concepts.csv and synonyms.csv", processed_dir)
        raise SystemExit(2)

    logger.info("Reading CSVs from %s", processed_dir)
    df_concepts = pd.read_csv(concepts_csv, dtype=str).fillna("")
    df_synonyms = pd.read_csv(synonyms_csv, dtype=str).fillna("")

    logger.info("Writing SQLite DB to %s", out_db)
    conn = sqlite3.connect(out_db)
    try:
        df_concepts.to_sql("concepts", conn, if_exists="replace", index=False)
        df_synonyms.to_sql("synonyms", conn, if_exists="replace", index=False)

        cur = conn.cursor()

        # idx_term_string: prefer concepts(term_string) if present, otherwise synonyms(term_string)
        if "term_string" in df_concepts.columns:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_term_string ON concepts(term_string)")
        elif "term_string" in df_synonyms.columns:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_term_string ON synonyms(term_string)")

        # create sui/cui indexes on both tables when columns exist (table-scoped names)
        if "sui" in df_concepts.columns:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sui_concepts ON concepts(sui)")
        if "sui" in df_synonyms.columns:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sui_synonyms ON synonyms(sui)")

        if "cui" in df_concepts.columns:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cui_concepts ON concepts(cui)")
        if "cui" in df_synonyms.columns:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cui_synonyms ON synonyms(cui)")

        conn.commit()
    finally:
        conn.close()

    logger.info("SQLite DB created: %s", out_db)


def main(argv: list[str] | None = None) -> None:
    import argparse

    p = argparse.ArgumentParser(description="Convert processed CSVs to SQLite DB (open_umls.db)")
    p.add_argument("--processed_dir", default=None, help="Directory containing processed CSVs (default: data/processed)")
    p.add_argument("--out", default=None, help="Output SQLite path (default: data/processed/open_umls.db)")
    args = p.parse_args(argv)

    csv_to_sqlite(args.processed_dir, args.out)


if __name__ == "__main__":
    main(sys.argv[1:])
