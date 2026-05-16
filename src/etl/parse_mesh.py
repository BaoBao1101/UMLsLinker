"""MeSH XML parser using streaming `lxml.etree.iterparse`.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from typing import Generator, List, Tuple

from lxml import etree

logger = logging.getLogger(__name__)


def _normalize_term(s: str) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.lower()
    s = re.sub(r"[\W_]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _generate_sui(cui: str, term: str) -> str:
    key = f"{cui}||{term}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def iter_mesh_records(xml_path: str) -> Generator[Tuple[str, str, List[str]], None, None]:
    """Stream-parse a MeSH XML file and yield (cui, canonical_name, synonyms, tree_numbers).

    The function uses `lxml.etree.iterparse` and clears parsed elements to keep
    memory usage low. Returned `cui` values are prefixed with `MESH:`. The
    additional `tree_numbers` list contains MeSH TreeNumber strings (if any)
    which can be used to infer semantic category (e.g. 'C' = Diseases,
    'D' = Chemicals).
    """
    context = etree.iterparse(xml_path, events=("end",), recover=True)
    for event, elem in context:
        try:
            tag = etree.QName(elem.tag).localname
        except Exception:
            tag = str(elem.tag)

        # Only process DescriptorRecord elements; do not eagerly clear until after processing to ensure we can access child elements
        if tag == "DescriptorRecord":
            descriptor_ui_list = elem.xpath('.//*[local-name()="DescriptorUI"]/text()')
            descriptor_ui = descriptor_ui_list[0].strip() if descriptor_ui_list else None

            descriptor_name_list = elem.xpath(
                './/*[local-name()="DescriptorName"]/*[local-name()="String"]/text()'
            )
            descriptor_name = descriptor_name_list[0].strip() if descriptor_name_list else ""

            synonyms = elem.xpath(
                './/*[local-name()="ConceptList"]//*[local-name()="Term"]/*[local-name()="String"]/text()'
            )
            synonyms = [s.strip() for s in synonyms if s and s.strip()]
            if descriptor_name and descriptor_name not in synonyms:
                synonyms.insert(0, descriptor_name)

            if descriptor_ui:
                cui = f"MESH:{descriptor_ui}"
            else:
                sui_stub = _generate_sui("MESH", descriptor_name or "")[:8]
                cui = f"MESH:UNKN_{sui_stub}"

            # extract MeSH TreeNumber
            tree_numbers = elem.xpath('.//*[local-name()="TreeNumberList"]/*[local-name()="TreeNumber"]/text()')
            tree_numbers = [t.strip() for t in tree_numbers if t and t.strip()]

            # yield canonical name, raw synonyms and tree numbers
            yield (cui, descriptor_name or "", synonyms, tree_numbers)

            # free memory used by the element and it sibling
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]

    del context


def iter_mesh_records_detailed(xml_path: str) -> Generator[Tuple[str, str, List[str], List[str], Dict[str, List[str]]], None, None]:
    context = etree.iterparse(xml_path, events=("end",), recover=True)
    for event, elem in context:
        try:
            tag = etree.QName(elem.tag).localname
        except Exception:
            tag = str(elem.tag)

        if tag == "DescriptorRecord":
            descriptor_ui_list = elem.xpath('.//*[local-name()="DescriptorUI"]/text()')
            descriptor_ui = descriptor_ui_list[0].strip() if descriptor_ui_list else None

            descriptor_name_list = elem.xpath(
                './/*[local-name()="DescriptorName"]/*[local-name()="String"]/text()'
            )
            descriptor_name = descriptor_name_list[0].strip() if descriptor_name_list else ""

            synonyms = elem.xpath(
                './/*[local-name()="ConceptList"]//*[local-name()="Term"]/*[local-name()="String"]/text()'
            )
            synonyms = [s.strip() for s in synonyms if s and s.strip()]
            if descriptor_name and descriptor_name not in synonyms:
                synonyms.insert(0, descriptor_name)

            if descriptor_ui:
                cui = f"MESH:{descriptor_ui}"
            else:
                sui_stub = _generate_sui("MESH", descriptor_name or "")[:8]
                cui = f"MESH:UNKN_{sui_stub}"

            tree_numbers = elem.xpath('.//*[local-name()="TreeNumberList"]/*[local-name()="TreeNumber"]/text()')
            tree_numbers = [t.strip() for t in tree_numbers if t and t.strip()]

            # scope note(s)
            scope_notes = elem.xpath('.//*[local-name()="ScopeNote"]/text()')
            scope_notes = [s.strip() for s in scope_notes if s and s.strip()]

            # registry numbers (chemical RNs)
            registry_numbers = elem.xpath('.//*[local-name()="RegistryNumberList"]/*[local-name()="RegistryNumber"]/text()')
            registry_numbers = [r.strip() for r in registry_numbers if r and r.strip()]

            meta = {
                "definitions": scope_notes,
                "xrefs": registry_numbers,
            }

            yield (cui, descriptor_name or "", synonyms, tree_numbers, meta)

            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]

    del context
