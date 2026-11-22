"""Adapter for the read-only Part 1 handoff; no index rebuild or model download."""
from functools import partial
from pathlib import Path
import sys


class PolicyAgent:
    def __init__(self, handoff_path=None):
        root = Path(handoff_path or Path(__file__).resolve().parent.parent / "part1_handoff").resolve()
        if not (root / "policy_rag" / "retrieve.py").is_file():
            raise FileNotFoundError(f"Part 1 handoff not found: {root}")
        existing = sys.modules.get("policy_rag.retrieve")
        if existing and Path(existing.ROOT).resolve() != root:
            raise ValueError("A different Part 1 handoff is already loaded in this process")
        sys.path.insert(0, str(root))
        from policy_rag.retrieve import PolicyRetriever
        from policy_rag.verify import verify_claims
        self.retriever = PolicyRetriever(root / "data" / "policy_index.sqlite")
        self.verify_claims = partial(verify_claims, db_path=root / "data" / "policy_index.sqlite",
                                     source_root=root)

    def search(self, question, **filters):
        # BM25 works entirely locally. Supervisor translates Chinese search queries
        # to English because the supplied lexical index contains English passages.
        return self.retriever.search(question, method="bm25", **filters)
