"""Example for the teammate implementing the Policy Agent. No LLM needed."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy_rag.retrieve import PolicyRetriever

retriever = PolicyRetriever()  # Construct once, reuse for multiple questions.
evidence = retriever.search(
    'Can I drop a subject after the add/drop period?',
    academic_year='2026/27', student_type='taught_postgraduate', top_k=3,
)
print(json.dumps(evidence, ensure_ascii=False, indent=2))
# Pass evidence['results'] to the Answerer; never send only relevance scores.
# If a rule may continue on the next page:
# surrounding_evidence = retriever.context(evidence['results'][0]['evidence_id'])
