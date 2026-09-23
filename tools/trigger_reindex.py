"""Ask the running bot to reindex the knowledge base on its next maintenance tick."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.core.rag_utils import reindex_trigger_path, request_reindex

if __name__ == "__main__":
    if request_reindex():
        print(f"RAG reindex requested ({reindex_trigger_path()}).")
    else:
        print("Could not write the reindex trigger.", file=sys.stderr)
        sys.exit(1)
