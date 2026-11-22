"""Offline checks. Optionally pass an extracted Part 1 folder as argv[1]."""
import json
from pathlib import Path
import sys

from agents import answer, collect_evidence, verify


def main():
    gate = None
    fact = "COMP5926 requires COMP5925 Metaverse Project I."
    quote = "Pre-requisite: COMP5925 Metaverse Project I"
    policy = {"status": "candidates_found", "results": [
        {"evidence_id": "policy-example", "text": quote, "citation": {"title": "Test subject form"}}
    ]}
    if len(sys.argv) > 1:
        root = Path(sys.argv[1]).resolve()
        sys.path.insert(0, str(root))
        from policy_rag.retrieve import PolicyRetriever
        from policy_rag.verify import verify_claims
        gate = verify_claims
        policy = PolicyRetriever().search("What is the prerequisite for COMP5926?", method="bm25")
    key = next(row["evidence_id"] for row in policy["results"] if quote in row["text"])
    bundle = collect_evidence(policy, [
        {"evidence_id": "schedule:example", "text": "COMP5926 class: 14:00",
         "citation": {"title": "Mock schedule"}}
    ])
    question = "What is the prerequisite for COMP5926 and when is its class?"

    def draft_model(system, payload):
        return {"claims": [
            {"text": fact, "supports": [{"evidence_id": key, "quote": quote}]},
            {"text": "The class is at 14:00.", "supports": [
                {"evidence_id": "schedule:example", "quote": "COMP5926 class: 14:00"}]}
        ]}

    def review_model(system, payload):
        return {"checks": [
            {"index": i, "status": "contradicted" if "15:00" in c["text"] else "supported",
             "reason": "Fixture verdict for the class time and prerequisite."}
            for i, c in enumerate(payload["claims"])],
            "unanswered": ["class location"] if "location" in payload["question"] else [],
            "needs_clarification": False}

    draft = answer(question, bundle, draft_model)
    passed = verify(question, bundle, draft, review_model, gate)
    assert passed["approved"], passed
    assert verify(question + " And the location?", bundle, draft, review_model, gate)["status"] == "insufficient_evidence"
    draft["claims"][1]["text"] = "The class is at 15:00."
    assert verify(question, bundle, draft, review_model, gate)["status"] == "rejected"
    draft["claims"][1]["supports"][0]["quote"] = "COMP5926 class: 15:00"
    assert verify(question, bundle, draft, review_model, gate)["status"] == "rejected"
    empty = collect_evidence({"status": "no_year_specific_evidence", "results": []})
    assert verify(question, empty, answer(question, empty, draft_model), review_model)["status"] == "insufficient_evidence"
    print(json.dumps(passed, ensure_ascii=False, indent=2))
    print("5 offline cases passed. Model outputs were simulated.")


if __name__ == "__main__":
    main()
