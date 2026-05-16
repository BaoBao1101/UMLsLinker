"""Safe test for NeuralLinker that does not build the full index.

It attempts to import the class and reports whether an index exists. It does
not run `build_index` (heavy) unless the user explicitly changes the script.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "src"))

from linker.neural_linker import NeuralLinker


def main():
    nl = NeuralLinker(db_path="data/processed/open_umls.db")
    print("NeuralLinker initialized")
    if nl.index_exists():
        print("Index found at", nl.index_dir)
    else:
        print("No index found. To build embeddings, call nn.build_index(...)")


if __name__ == "__main__":
    main()
