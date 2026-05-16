from __future__ import annotations

import os
import sys
import duckdb

candidates = [
    "data/processed/open_umls_phase5.db",
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

try:
    total_concepts = conn.execute("SELECT count(*) FROM concepts").fetchone()[0]
    total_synonyms = conn.execute("SELECT count(*) FROM synonyms").fetchone()[0]
except Exception as e:
    print("Error querying tables:", e)
    sys.exit(3)

print(f"Total concepts: {total_concepts}")
print(f"Total synonyms: {total_synonyms}")

print("\nTop semantic_type by concept count:")
rows_sem = conn.execute(
    "SELECT COALESCE(semantic_type,'UNKNOWN') as sem, count(*) as cnt FROM concepts GROUP BY sem ORDER BY cnt DESC LIMIT 50"
).fetchall()
for sem, cnt in rows_sem:
    print(f" - {sem}: {cnt}")

print("\nTop source_ontology by concept count:")
rows = conn.execute(
    "SELECT COALESCE(source_ontology, 'UNKNOWN') as src, count(*) as cnt FROM concepts GROUP BY src ORDER BY cnt DESC LIMIT 50"
).fetchall()
for src, cnt in rows:
    print(f" - {src}: {cnt}")

sample_sources = ["HP", "MONDO", "CHEBI"]
for s in sample_sources:
    print(f"\nSample concepts for source '{s}':")
    recs = conn.execute(f"SELECT cui, canonical_name FROM concepts WHERE UPPER(COALESCE(source_ontology,'')) = '{s}' LIMIT 5").fetchall()
    if not recs:
        print("  (no records found)")
        continue
    for cui, name in recs:
        print(f"  {cui}\t{name}")
        syns = conn.execute(f"SELECT term_string FROM synonyms WHERE cui = '{cui}' LIMIT 5").fetchall()
        syns = [r[0] for r in syns]
        print("    synonyms:", syns)

# show a few sample MeSH entries
print("\nSample MeSH concepts:")
mesh_recs = conn.execute("SELECT cui, canonical_name FROM concepts WHERE UPPER(COALESCE(source_ontology,'')) = 'MESH' LIMIT 5").fetchall()
for cui, name in mesh_recs:
    print(f"  {cui}\t{name}")

conn.close()
