#!/usr/bin/env python3
"""Quick parser checker: iterate raw ontology files and report counts/samples.

This script uses the existing OBO parser (with fallback) and a lightweight
MeSH XML iterator that does not require `lxml` so it can run in minimal
environments for quick validation.
"""
from __future__ import annotations

import glob
import hashlib
import os
import sys

# ensure local ETL imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "etl"))
from parse_obo import iter_ontology_terms  # type: ignore

import xml.etree.ElementTree as ET


def _localname(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def iter_mesh_records_simple(xml_path: str):
    """Lightweight MeSH iterator using stdlib ElementTree (memory-conscious).

    Yields (cui, canonical_name, synonyms, tree_numbers).
    """
    context = ET.iterparse(xml_path, events=("end",))
    for event, elem in context:
        if _localname(elem.tag) == "DescriptorRecord":
            descriptor_ui = None
            descriptor_name = ""
            synonyms = []
            tree_numbers = []

            for child in elem.iter():
                ln = _localname(child.tag)
                if ln == "DescriptorUI" and child.text and not descriptor_ui:
                    descriptor_ui = child.text.strip()
                elif ln == "DescriptorName" and not descriptor_name:
                    for sub in child.iter():
                        if _localname(sub.tag) == "String" and sub.text:
                            descriptor_name = sub.text.strip()
                            break
                elif ln == "Term":
                    for sub in child.iter():
                        if _localname(sub.tag) == "String" and sub.text:
                            synonyms.append(sub.text.strip())
                elif ln == "TreeNumber" and child.text:
                    tree_numbers.append(child.text.strip())

            if descriptor_name and descriptor_name not in synonyms:
                synonyms.insert(0, descriptor_name)

            if descriptor_ui:
                cui = f"MeSH:{descriptor_ui}"
            else:
                sui_stub = hashlib.sha1(f"MeSH||{descriptor_name}".encode("utf-8")).hexdigest()[:8]
                cui = f"MeSH:UNKN_{sui_stub}"

            yield (cui, descriptor_name or "", synonyms, tree_numbers)

            # clear to save memory
            elem.clear()
    del context


def main() -> None:
    repo_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    raw_dir = os.path.join(repo_root, "data", "raw")

    if not os.path.exists(raw_dir):
        print("Raw data directory not found:", raw_dir)
        sys.exit(2)

    obos = glob.glob(os.path.join(raw_dir, "*.obo"))
    xmls = glob.glob(os.path.join(raw_dir, "*.xml"))

    print("Raw dir:", raw_dir)

    # OBO files
    for ob in obos:
        print("\nOBO file:", os.path.basename(ob))
        term_count = 0
        syn_total = 0
        samples = []
        for tid, name, syns in iter_ontology_terms(ob):
            term_count += 1
            syn_total += len(syns or [])
            if len(samples) < 5:
                samples.append((tid, name, (syns or [])[:5]))
        print(f"  terms: {term_count}, synonyms total: {syn_total}, avg syns/term: {syn_total/term_count if term_count else 0:.2f}")
        print("  samples:")
        for s in samples:
            print("   ", s)

    # MeSH
    if xmls:
        mesh = xmls[0]
        print("\nMeSH file:", os.path.basename(mesh))
        concept_count = 0
        syn_total = 0
        samples = []
        for cui, name, syns, trees in iter_mesh_records_simple(mesh):
            concept_count += 1
            syn_total += len(syns or [])
            if len(samples) < 5:
                samples.append((cui, name, (syns or [])[:5], (trees or [])[:3]))
        print(f"  concepts: {concept_count}, synonyms total: {syn_total}, avg syns/concept: {syn_total/concept_count if concept_count else 0:.2f}")
        print("  samples:")
        for s in samples:
            print("   ", s)
    else:
        print("\nNo MeSH XML found in raw dir")


if __name__ == "__main__":
    main()
