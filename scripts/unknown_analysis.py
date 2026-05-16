from __future__ import annotations

import os
import sys
import duckdb

candidates = [
    "data/processed/open_umls_phase4.db",
    "data/processed/open_umls_phase3.db",
    "data/processed/open_umls_phase2.db",
    "data/processed/open_umls_test.db",
    "data/processed/open_umls.db",
]

db_path = None
for p in candidates:
    if os.path.exists(p):
        db_path = p
        break

if db_path is None:
    print("No processed DB found in:", candidates)
    sys.exit(2)

print("Using DB:", db_path)
conn = duckdb.connect(db_path)

q_missing = "SELECT count(*) FROM concepts WHERE semantic_type IS NULL OR trim(semantic_type) = ''"
missing = conn.execute(q_missing).fetchone()[0]
print(f"Missing semantic_type count: {missing}")

print("\nTop source_ontology among missing semantic_type:")
rows = conn.execute(
    "SELECT COALESCE(source_ontology,'(empty)') as src, count(*) as cnt FROM concepts WHERE semantic_type IS NULL OR trim(semantic_type) = '' GROUP BY src ORDER BY cnt DESC LIMIT 50"
).fetchall()
for src, cnt in rows:
    print(f" - {src}: {cnt}")

# show sample rows for top 5 sources
top_sources = [r[0] for r in rows[:5]]
for s in top_sources:
    print(f"\nSamples for source: {s}")
    recs = conn.execute(f"SELECT cui, canonical_name FROM concepts WHERE (semantic_type IS NULL OR trim(semantic_type) = '') AND COALESCE(source_ontology,'') = '{s}' LIMIT 10").fetchall()
    if not recs:
        print(" (none)")
        continue
    for cui, name in recs:
        print(f"  {cui}\t{name}")
        syns = conn.execute(f"SELECT term_string FROM synonyms WHERE cui = '{cui}' LIMIT 5").fetchall()
        print("    synonyms:", [x[0] for x in syns])

conn.close()
