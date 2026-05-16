"""OBO/OWL parser using `pronto`.

Provides a generator that yields (id, name, synonyms) for terms in an OBO/OWL
ontology file. The function is intentionally tolerant of differing synonym
representations so it works with HPO, MONDO and similar ontologies.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from typing import Generator, List, Tuple, Dict

logger = logging.getLogger(__name__)


def _normalize_syn_obj(syn_obj) -> str:
    for attr in ("description", "desc", "text", "name"):
        val = getattr(syn_obj, attr, None)
        if val:
            return str(val).strip()
    return str(syn_obj).strip()


def _iter_obo_fallback(path: str) -> Generator[Tuple[str, str, List[str]], None, None]:
    """Simple fallback OBO parser that extracts id, name, and synonyms.

    This does not attempt to build relations; it's resilient to missing
    imports and external references which can break full parsers.
    """
    term_block = None
    tid = None
    name = None
    synonyms: List[str] = []

    def _emit():
        nonlocal tid, name, synonyms
        if tid:
            if name and name not in synonyms:
                synonyms.insert(0, name)
            yield_tid = tid
            yield_name = name or ""
            yield_syns = list(dict.fromkeys([s for s in synonyms if s]))
            yield (yield_tid, yield_name, yield_syns)

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if line == "[Term]":
                # emit previous
                if tid:
                    for out in _emit():
                        yield out
                # reset
                tid = None
                name = None
                synonyms = []
                continue

            if line.startswith("id:"):
                tid = line.split("id:", 1)[1].strip()
                continue
            if line.startswith("name:"):
                name = line.split("name:", 1)[1].strip()
                continue
            # synonyms can appear as: synonym: "..." EXACT [] or exact_synonym: "..."
            m2 = re.match(r'^exact_synonym:\s*"(.*?)"', line)
            if m2:
                synonyms.append(m2.group(1).strip())
                continue
            m = re.match(r'^synonym:\s*"(.*?)"', line)
            # accept all synonym lines (not just EXACT) to capture related terms
            if m:
                synonyms.append(m.group(1).strip())
                continue
            # skip obsolete terms
            if line.startswith("is_obsolete:") and "true" in line:
                tid = None
                name = None
                synonyms = []
                continue

    # emit last
    if tid:
        if name and name not in synonyms:
            synonyms.insert(0, name)
        yield (tid, name or "", list(dict.fromkeys([s for s in synonyms if s])))


def _iter_obo_fallback_extended(path: str) -> Generator[Tuple[str, str, List[str], Dict[str, List[str]]], None, None]:
    """Extended fallback parser that also extracts defs, xrefs, parents and alt_ids.

    Yields tuples: (id, name, synonyms, meta_dict)
    where meta_dict contains keys: 'definitions', 'xrefs', 'parents', 'alt_ids'
    """
    term_block = None
    tid = None
    name = None
    synonyms: List[str] = []
    definitions: List[str] = []
    xrefs: List[str] = []
    parents: List[str] = []
    alt_ids: List[str] = []

    def _emit():
        nonlocal tid, name, synonyms, definitions, xrefs, parents, alt_ids
        if tid:
            if name and name not in synonyms:
                synonyms.insert(0, name)
            yield_tid = tid
            yield_name = name or ""
            yield_syns = list(dict.fromkeys([s for s in synonyms if s]))
            meta = {
                "definitions": list(dict.fromkeys([d for d in definitions if d])),
                "xrefs": list(dict.fromkeys([x for x in xrefs if x])),
                "parents": list(dict.fromkeys([p for p in parents if p])),
                "alt_ids": list(dict.fromkeys([a for a in alt_ids if a])),
            }
            yield (yield_tid, yield_name, yield_syns, meta)

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if line == "[Term]":
                # emit previous
                if tid:
                    for out in _emit():
                        yield out
                # reset
                tid = None
                name = None
                synonyms = []
                definitions = []
                xrefs = []
                parents = []
                alt_ids = []
                continue

            if line.startswith("id:"):
                tid = line.split("id:", 1)[1].strip()
                continue
            if line.startswith("name:"):
                name = line.split("name:", 1)[1].strip()
                continue
            # synonyms can appear as: synonym: "..." EXACT [] or exact_synonym: "..."
            m2 = re.match(r'^exact_synonym:\s*"(.*?)"', line)
            if m2:
                synonyms.append(m2.group(1).strip())
                continue
            m = re.match(r'^synonym:\s*"(.*?)"', line)
            if m:
                synonyms.append(m.group(1).strip())
                continue
            # definition
            mdef = re.match(r'^def:\s*"(.*?)"', line)
            if mdef:
                definitions.append(mdef.group(1).strip())
                continue
            # xref
            if line.startswith("xref:"):
                xrefs.append(line.split("xref:", 1)[1].strip())
                continue
            # alt ids
            if line.startswith("alt_id:"):
                alt_ids.append(line.split("alt_id:", 1)[1].strip())
                continue
            # is_a relations
            if line.startswith("is_a:"):
                parent = line.split("is_a:", 1)[1].strip().split()[0]
                parents.append(parent)
                continue
            # generic relationship: e.g. relationship: part_of CHEBI:xxx ! name
            mrel = re.match(r'^relationship:\s*(\S+)\s+(\S+)', line)
            if mrel:
                rel_type = mrel.group(1).strip()
                target = mrel.group(2).strip()
                parents.append(target)
                continue
            # skip obsolete terms
            if line.startswith("is_obsolete:") and "true" in line:
                tid = None
                name = None
                synonyms = []
                definitions = []
                xrefs = []
                parents = []
                alt_ids = []
                continue

    # emit last
    if tid:
        if name and name not in synonyms:
            synonyms.insert(0, name)
        meta = {
            "definitions": list(dict.fromkeys([d for d in definitions if d])),
            "xrefs": list(dict.fromkeys([x for x in xrefs if x])),
            "parents": list(dict.fromkeys([p for p in parents if p])),
            "alt_ids": list(dict.fromkeys([a for a in alt_ids if a])),
        }
        yield (tid, name or "", list(dict.fromkeys([s for s in synonyms if s])), meta)


def iter_ontology_terms(ontology_path: str) -> Generator[Tuple[str, str, List[str]], None, None]:
    """Yield (id, name, synonyms) for each non-obsolete term in the ontology.

    Try `pronto` first for OWL/complex parsing; if it fails, fall back to a
    lightweight OBO parser that extracts basic fields.
    """
    try:
        import pronto 

        def _load_with_fallback(path: str):
            """Try loading with pronto; if it fails, attempt to re-decode file
            into UTF-8 via several encodings and retry using a temporary file.
            """
            try:
                return pronto.Ontology(path)
            except Exception as e:
                logger.debug("pronto failed to load %s: %s", path, e)
                # Try reading bytes and re-decoding with common encodings
                encodings = ["utf-8", "utf-8-sig", "iso-8859-1", "cp1252", "latin-1"]
                with open(path, "rb") as fh:
                    data = fh.read()
                for enc in encodings:
                    try:
                        text = data.decode(enc)
                    except Exception:
                        continue
                    # write to temp file in utf-8
                    tf = tempfile.NamedTemporaryFile("w", delete=False, suffix=os.path.basename(path), encoding="utf-8")
                    try:
                        tf.write(text)
                        tf.close()
                        ont = pronto.Ontology(tf.name)
                        return ont
                    except Exception as e2:
                        logger.debug("pronto failed on re-encoded file (%s): %s", enc, e2)
                    finally:
                        try:
                            os.unlink(tf.name)
                        except Exception:
                            pass
                # give up
                raise

        ont = _load_with_fallback(ontology_path)
        for term in ont.terms():
            try:
                if getattr(term, "obsolete", False):
                    continue
            except Exception:
                pass

            tid = str(term.id)
            name = term.name or ""

            synonyms: List[str] = []
            try:
                for syn in getattr(term, "synonyms", []) or []:
                    # include all synonym scopes for better coverage
                    try:
                        txt = _normalize_syn_obj(syn)
                    except Exception:
                        try:
                            txt = str(syn).strip()
                        except Exception:
                            txt = None
                    if txt:
                        synonyms.append(txt)
            except Exception:
                # fallback: some ontologies expose synonyms differently
                pass

            if name and name not in synonyms:
                synonyms.insert(0, name)

            yield (tid, name, synonyms)
    except Exception as exc:  # pragma: no cover - runtime fallback
        logger.warning("pronto failed to load %s (%s); using simple OBO fallback", ontology_path, exc)
        # only fallback for OBO-like files
        if ontology_path.lower().endswith(".obo"):
            yield from _iter_obo_fallback(ontology_path)
        else:
            logger.error("No fallback available for %s; skipping", ontology_path)
            return


def iter_ontology_terms_detailed(ontology_path: str) -> Generator[Tuple[str, str, List[str], Dict[str, List[str]]], None, None]:
    """Yield (id, name, synonyms, meta) where meta includes definitions, xrefs, parents, alt_ids.

    This function is a superset of `iter_ontology_terms` and can be used when
    richer metadata is required for building relationships or UML-like graphs.
    """
    try:
        import pronto  # type: ignore

        def _load_with_fallback(path: str):
            try:
                return pronto.Ontology(path)
            except Exception as e:
                logger.debug("pronto failed to load %s: %s", path, e)
                encodings = ["utf-8", "utf-8-sig", "iso-8859-1", "cp1252", "latin-1"]
                with open(path, "rb") as fh:
                    data = fh.read()
                for enc in encodings:
                    try:
                        text = data.decode(enc)
                    except Exception:
                        continue
                    tf = tempfile.NamedTemporaryFile("w", delete=False, suffix=os.path.basename(path), encoding="utf-8")
                    try:
                        tf.write(text)
                        tf.close()
                        ont = pronto.Ontology(tf.name)
                        return ont
                    except Exception as e2:
                        logger.debug("pronto failed on re-encoded file (%s): %s", enc, e2)
                    finally:
                        try:
                            os.unlink(tf.name)
                        except Exception:
                            pass
                raise

        ont = _load_with_fallback(ontology_path)
        for term in ont.terms():
            try:
                if getattr(term, "obsolete", False):
                    continue
            except Exception:
                pass

            tid = str(term.id)
            name = term.name or ""

            synonyms: List[str] = []
            definitions: List[str] = []
            xrefs: List[str] = []
            parents: List[str] = []
            alt_ids: List[str] = []

            try:
                for syn in getattr(term, "synonyms", []) or []:
                    try:
                        txt = _normalize_syn_obj(syn)
                    except Exception:
                        try:
                            txt = str(syn).strip()
                        except Exception:
                            txt = None
                    if txt:
                        synonyms.append(txt)
            except Exception:
                pass

            # definitions
            try:
                d = getattr(term, "definition", None)
                if d:
                    if isinstance(d, (list, tuple)):
                        definitions.extend([str(x).strip() for x in d if x])
                    else:
                        definitions.append(str(d).strip())
            except Exception:
                pass

            # xrefs
            try:
                for x in getattr(term, "xrefs", []) or []:
                    xrefs.append(str(x).strip())
            except Exception:
                pass

            # alt_ids
            try:
                for a in getattr(term, "alt_ids", []) or []:
                    alt_ids.append(str(a).strip())
            except Exception:
                pass

            # parents / relations: probe multiple attributes
            for attr in ("parents", "superclasses", "rparents", "is_a", "ancestors"):
                try:
                    val = getattr(term, attr, None)
                    if not val:
                        continue
                    items = list(val() if callable(val) else val)
                    for p in items:
                        try:
                            pid = getattr(p, "id", None) or str(p)
                        except Exception:
                            pid = str(p)
                        if pid:
                            parents.append(str(pid))
                except Exception:
                    continue

            # dedupe and ensure canonical name present in synonyms
            synonyms = list(dict.fromkeys([s for s in synonyms if s]))
            if name and name not in synonyms:
                synonyms.insert(0, name)

            meta: Dict[str, List[str]] = {
                "definitions": list(dict.fromkeys([d for d in definitions if d])),
                "xrefs": list(dict.fromkeys([x for x in xrefs if x])),
                "parents": list(dict.fromkeys([p for p in parents if p])),
                "alt_ids": list(dict.fromkeys([a for a in alt_ids if a])),
            }

            yield (tid, name, synonyms, meta)
    except Exception as exc:  # pragma: no cover - runtime fallback
        logger.warning("pronto failed to load %s (%s); using extended OBO fallback", ontology_path, exc)
        if ontology_path.lower().endswith(".obo"):
            yield from _iter_obo_fallback_extended(ontology_path)
        else:
            logger.error("No fallback available for %s; skipping", ontology_path)
            return
