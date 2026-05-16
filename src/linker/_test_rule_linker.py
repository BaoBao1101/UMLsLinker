"""Quick sanity test for the RuleLinker.

This script is intended to be run from the repository root to verify the
deterministic linker can load the processed DB and find simple matches.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "src"))

from linker.rule_linker import RuleLinker


def main():
    rl = RuleLinker(db_path="data/processed/open_umls.db")
    text = "patient shows severe low back pain and uses aspirin"
    matches = rl.match_text(text)
    print("Found", len(matches), "matches")
    for m in matches[:20]:
        print(m)


if __name__ == "__main__":
    main()
