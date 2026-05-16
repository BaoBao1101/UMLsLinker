from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import logging
import os
import re
import sys
from typing import Iterable, List, Set, Tuple

import duckdb
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))

from parse_mesh import iter_mesh_records, iter_mesh_records_detailed  # type: ignore
from parse_obo import iter_ontology_terms, iter_ontology_terms_detailed  # type: ignore

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# Semantic mapping tables
SEMANTIC_MAP = {
    "HP": "T_SYMPTOM",
    "MONDO": "T_DISEASE",
    "DOID": "T_DISEASE",
    "OMIM": "T_DISEASE",
    "CHEBI": "T_DRUG",
    "CHEMBL": "T_DRUG",
}

# MeSH tree-number
MESH_TREE_TO_SEMANTIC = {
    "A": "T_ANATOMY",
    "C": "T_DISEASE",
    "D": "T_DRUG",
    "E01": "T_PARACLINICAL",
    "E04": "T_TREATMENT",
    "F": "T_SYMPTOM",
}


def _infer_semantic_from_src_and_path(src: str | None, ontology_path: str | None) -> str | None:
    if src:
        sem = SEMANTIC_MAP.get(src.upper())
        if sem:
            return sem
    if ontology_path:
        low = os.path.basename(ontology_path).lower()
        if "hp" in low or "hpo" in low:
            return "T_SYMPTOM"
        if "mondo" in low:
            return "T_DISEASE"
        if "chebi" in low:
            return "T_DRUG"
        # Do not force a Mesh tag here; MeSH is handled via tree numbers.
    return None


def _normalize_term(s: str) -> str:
    if s is None:
        return ""
    s = (s or "").strip().lower()
    s = re.sub(r"[\W_]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _generate_sui(cui: str, term: str) -> str:
    return hashlib.sha1(f"{cui}||{term}".encode("utf-8")).hexdigest()


def _ensure_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS concepts (
            cui TEXT PRIMARY KEY,
            canonical_name TEXT,
            source_ontology TEXT,
            semantic_type TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS synonyms (
            sui TEXT PRIMARY KEY,
            cui TEXT,
            term_string TEXT,
            is_normalized BOOLEAN
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS definitions (
            cui TEXT,
            definition TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS relations (
            cui TEXT,
            rel_type TEXT,
            target_cui TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS xrefs (
            cui TEXT,
            xref TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alt_ids (
            cui TEXT,
            alt_id TEXT
        )
        """
    )


def _insert_chunk(
    conn: duckdb.DuckDBPyConnection,
    concepts: List[Tuple[str, str, str, str]],
    synonyms: List[Tuple[str, str, str, bool]],
    definitions: List[Tuple[str, str]] | None = None,
    relations: List[Tuple[str, str, str]] | None = None,
    xrefs: List[Tuple[str, str]] | None = None,
    alt_ids: List[Tuple[str, str]] | None = None,
):
    if concepts:
        df_c = pd.DataFrame(concepts, columns=["cui", "canonical_name", "source_ontology", "semantic_type"])
        conn.register("df_chunk_concepts", df_c)
        conn.execute("INSERT INTO concepts SELECT * FROM df_chunk_concepts")
    if synonyms:
        df_s = pd.DataFrame(synonyms, columns=["sui", "cui", "term_string", "is_normalized"])
        conn.register("df_chunk_synonyms", df_s)
        conn.execute("INSERT INTO synonyms SELECT * FROM df_chunk_synonyms")
    if definitions:
        df_d = pd.DataFrame(definitions, columns=["cui", "definition"])
        conn.register("df_chunk_definitions", df_d)
        conn.execute("INSERT INTO definitions SELECT * FROM df_chunk_definitions")
    if relations:
        df_r = pd.DataFrame(relations, columns=["cui", "rel_type", "target_cui"])
        conn.register("df_chunk_relations", df_r)
        conn.execute("INSERT INTO relations SELECT * FROM df_chunk_relations")
    if xrefs:
        df_x = pd.DataFrame(xrefs, columns=["cui", "xref"])
        conn.register("df_chunk_xrefs", df_x)
        conn.execute("INSERT INTO xrefs SELECT * FROM df_chunk_xrefs")
    if alt_ids:
        df_a = pd.DataFrame(alt_ids, columns=["cui", "alt_id"])
        conn.register("df_chunk_altids", df_a)
        conn.execute("INSERT INTO alt_ids SELECT * FROM df_chunk_altids")


def build_database(raw_dir: str, mesh_path: str | None, ontology_paths: Iterable[str], out_db: str, out_dir: str | None = None, chunk_size: int = 2000, overwrite: bool = False, write_csv: bool = True) -> None:
    out_dir = out_dir or os.path.dirname(out_db) or "data/processed"
    os.makedirs(out_dir, exist_ok=True)

    if overwrite and os.path.exists(out_db):
        try:
            os.remove(out_db)
        except Exception:
            logger.debug("Could not remove existing DB file")

    conn = duckdb.connect(out_db)
    _ensure_tables(conn)

    existing_cuis: Set[str] = set()
    existing_suis: Set[str] = set()
    existing_defs: Set[Tuple[str, str]] = set()
    existing_rels: Set[Tuple[str, str, str]] = set()
    existing_xrefs: Set[Tuple[str, str]] = set()
    existing_altids: Set[Tuple[str, str]] = set()

    concept_buffer: List[Tuple[str, str, str, str]] = []
    synonym_buffer: List[Tuple[str, str, str, bool]] = []
    definitions_buffer: List[Tuple[str, str]] = []
    relations_buffer: List[Tuple[str, str, str]] = []
    xrefs_buffer: List[Tuple[str, str]] = []
    altids_buffer: List[Tuple[str, str]] = []

    # prepare CSV writters
    concepts_csv = None
    synonyms_csv = None
    vector_meta_csv = None
    concepts_writer = synonyms_writer = vector_meta_writer = None

    if write_csv:
        concepts_csv = open(os.path.join(out_dir, "concepts.csv"), "w", newline="", encoding="utf-8")
        synonyms_csv = open(os.path.join(out_dir, "synonyms.csv"), "w", newline="", encoding="utf-8")
        vector_meta_csv = open(os.path.join(out_dir, "vector_meta.csv"), "w", newline="", encoding="utf-8")
        definitions_csv = open(os.path.join(out_dir, "definitions.csv"), "w", newline="", encoding="utf-8")
        relations_csv = open(os.path.join(out_dir, "relations.csv"), "w", newline="", encoding="utf-8")
        xrefs_csv = open(os.path.join(out_dir, "xrefs.csv"), "w", newline="", encoding="utf-8")
        alt_ids_csv = open(os.path.join(out_dir, "alt_ids.csv"), "w", newline="", encoding="utf-8")
        concepts_writer = csv.writer(concepts_csv)
        synonyms_writer = csv.writer(synonyms_csv)
        vector_meta_writer = csv.writer(vector_meta_csv)
        definitions_writer = csv.writer(definitions_csv)
        relations_writer = csv.writer(relations_csv)
        xrefs_writer = csv.writer(xrefs_csv)
        alt_ids_writer = csv.writer(alt_ids_csv)
        concepts_writer.writerow(["cui", "canonical_name", "source_ontology", "semantic_type"])
        synonyms_writer.writerow(["sui", "cui", "term_string", "is_normalized"])
        vector_meta_writer.writerow(["sui", "cui", "term_string"])
        definitions_writer.writerow(["cui", "definition"])
        relations_writer.writerow(["cui", "rel_type", "target_cui"])
        xrefs_writer.writerow(["cui", "xref"])
        alt_ids_writer.writerow(["cui", "alt_id"])

    def _flush_if_needed():
        nonlocal concept_buffer, synonym_buffer, definitions_buffer, relations_buffer, xrefs_buffer, altids_buffer
        # flush when any buffer grows large
        if (
            len(concept_buffer) >= chunk_size
            or len(synonym_buffer) >= chunk_size
            or len(definitions_buffer) >= chunk_size
            or len(relations_buffer) >= chunk_size
            or len(xrefs_buffer) >= chunk_size
            or len(altids_buffer) >= chunk_size
        ):
            _insert_chunk(conn, concept_buffer, synonym_buffer, definitions_buffer, relations_buffer, xrefs_buffer, altids_buffer)
            if write_csv and concepts_writer and synonyms_writer and vector_meta_writer:
                concepts_writer.writerows(concept_buffer)
                synonyms_writer.writerows(synonym_buffer)
                # SUI, CUI, TERM will be vector metadataa
                for s in synonym_buffer:
                    sui, cui, term_string, _ = s
                    vector_meta_writer.writerow([sui, cui, term_string])
                # write other CSVs
                if definitions_buffer:
                    definitions_writer.writerows(definitions_buffer)
                if relations_buffer:
                    relations_writer.writerows(relations_buffer)
                if xrefs_buffer:
                    xrefs_writer.writerows(xrefs_buffer)
                if altids_buffer:
                    alt_ids_writer.writerows(altids_buffer)
            concept_buffer, synonym_buffer, definitions_buffer, relations_buffer, xrefs_buffer, altids_buffer = [], [], [], [], [], []

    # concept and synm
    def _add_concept(cui: str, canonical_name: str, source: str, semantic: str | None, syns: List[str]):
        if cui not in existing_cuis:
            concept_buffer.append((cui, canonical_name or "", source, semantic or ""))
            existing_cuis.add(cui)
        for s in syns:
            norm = _normalize_term(s)
            if not norm:
                continue
            sui = _generate_sui(cui, norm)
            if sui in existing_suis:
                continue
            synonym_buffer.append((sui, cui, norm, True))
            existing_suis.add(sui)

    def _add_meta(cui: str, meta: dict | None) -> None:
        if not meta:
            return
        for d in meta.get("definitions", []) or []:
            if not d:
                continue
            tup = (cui, d)
            if tup in existing_defs:
                continue
            definitions_buffer.append(tup)
            existing_defs.add(tup)
        for x in meta.get("xrefs", []) or []:
            if not x:
                continue
            tup = (cui, x)
            if tup in existing_xrefs:
                continue
            xrefs_buffer.append(tup)
            existing_xrefs.add(tup)
        for p in meta.get("parents", []) or []:
            if not p:
                continue
            tup = (cui, "is_a", p)
            if tup in existing_rels:
                continue
            relations_buffer.append(tup)
            existing_rels.add(tup)
        for a in meta.get("alt_ids", []) or []:
            if not a:
                continue
            tup = (cui, a)
            if tup in existing_altids:
                continue
            altids_buffer.append(tup)
            existing_altids.add(tup)

    # Process MeSH 1st
    if mesh_path and os.path.exists(mesh_path):
        logger.info("Processing MeSH from %s", mesh_path)
        try:
            mesh_iterator = iter_mesh_records_detailed(mesh_path)
        except Exception:
            mesh_iterator = iter_mesh_records(mesh_path)

        for rec in mesh_iterator:
            # support (cui, name, syns), (cui, name, syns, tree_numbers)
            # and (cui, name, syns, tree_numbers, meta)
            if len(rec) == 5:
                cui, canonical_name, syns, tree_numbers, meta = rec
            elif len(rec) == 4:
                cui, canonical_name, syns, tree_numbers = rec
                meta = None
            else:
                cui, canonical_name, syns = rec
                tree_numbers = []
                meta = None

            semantic = None
            if tree_numbers:
                # match the longest mapping key that is a prefix of the tree number
                for tn in tree_numbers:
                    t = tn.strip().upper()
                    matched = None
                    for key in sorted(MESH_TREE_TO_SEMANTIC.keys(), key=lambda k: -len(k)):
                        if t.startswith(key):
                            matched = MESH_TREE_TO_SEMANTIC[key]
                            break
                    if matched:
                        semantic = matched
                        break
            # fallback semantic for MeSH if none matched
            if semantic is None:
                semantic = "T_MEDICAL_ENTITY"

            _add_concept(cui, canonical_name, "MESH", semantic, syns)
            _add_meta(cui, meta)
            _flush_if_needed()

    # Ontologies processing
    for op in ontology_paths:
        if not os.path.exists(op):
            logger.warning("Ontology path does not exist, skipping: %s", op)
            continue
        logger.info("Processing ontology: %s", op)
        # prefer detailed iterator when available
        try:
            iterator = iter_ontology_terms_detailed(op)
        except Exception:
            iterator = iter_ontology_terms(op)

        for rec in iterator:
            if len(rec) == 4:
                tid, name, syns, meta = rec
            else:
                tid, name, syns = rec
                meta = None

            src = tid.split(":")[0] if ":" in tid else os.path.splitext(os.path.basename(op))[0]
            semantic = _infer_semantic_from_src_and_path(src, op)
            _add_concept(tid, name or "", src, semantic, syns)
            _add_meta(tid, meta)
            _flush_if_needed()

    # final
    if concept_buffer or synonym_buffer or definitions_buffer or relations_buffer or xrefs_buffer or altids_buffer:
        _insert_chunk(conn, concept_buffer, synonym_buffer, definitions_buffer, relations_buffer, xrefs_buffer, altids_buffer)
        if write_csv and concepts_writer and synonyms_writer and vector_meta_writer:
            concepts_writer.writerows(concept_buffer)
            synonyms_writer.writerows(synonym_buffer)
            for s in synonym_buffer:
                sui, cui, term_string, _ = s
                vector_meta_writer.writerow([sui, cui, term_string])
            if definitions_buffer:
                definitions_writer.writerows(definitions_buffer)
            if relations_buffer:
                relations_writer.writerows(relations_buffer)
            if xrefs_buffer:
                xrefs_writer.writerows(xrefs_buffer)
            if altids_buffer:
                alt_ids_writer.writerows(altids_buffer)

    # close CSVs
    if concepts_csv:
        concepts_csv.close()
    if synonyms_csv:
        synonyms_csv.close()
    if vector_meta_csv:
        vector_meta_csv.close()
    if write_csv:
        definitions_csv.close()
        relations_csv.close()
        xrefs_csv.close()
        alt_ids_csv.close()

    logger.info("Database build complete: %s", out_db)


def _find_default_files(raw_dir: str) -> Tuple[str | None, List[str]]:
    mesh_candidate = os.path.join(raw_dir, "desc2026.xml")
    if not os.path.exists(mesh_candidate):
        xmls = glob.glob(os.path.join(raw_dir, "*.xml"))
        mesh_candidate = xmls[0] if xmls else None
    obos = glob.glob(os.path.join(raw_dir, "*.obo"))
    owls = glob.glob(os.path.join(raw_dir, "*.owl"))
    return mesh_candidate, obos + owls


def main(argv: List[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Build processed OpenUMLS DuckDB and CSVs from raw files")
    p.add_argument("--raw_dir", default="data/raw", help="Directory with raw ontology files")
    p.add_argument("--mesh", default=None, help="Explicit MeSH XML path (optional)")
    p.add_argument("--out", default="data/processed/open_umls_duck.db", help="Output DuckDB path")
    p.add_argument("--out_dir", default="data/processed", help="Directory to write CSV and vector meta")
    p.add_argument("--chunk_size", type=int, default=2000)
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--no_csv", dest="write_csv", action="store_false", help="Do not write CSV outputs")
    args = p.parse_args(argv)

    mesh_path = args.mesh
    if mesh_path is None:
        mesh_path, ontology_paths = _find_default_files(args.raw_dir)
    else:
        ontology_paths = glob.glob(os.path.join(args.raw_dir, "*.obo")) + glob.glob(os.path.join(args.raw_dir, "*.owl"))

    build_database(args.raw_dir, mesh_path, ontology_paths, args.out, out_dir=args.out_dir, chunk_size=args.chunk_size, overwrite=args.overwrite, write_csv=args.write_csv)


if __name__ == "__main__":
    main()
