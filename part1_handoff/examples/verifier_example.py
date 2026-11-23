"""Offline example: Answerer claims -> integrity gate -> semantic Verifier review."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from policy_rag.retrieve import PolicyRetriever
from policy_rag.verify import verify_claims, VERIFIER_INSTRUCTIONS

def main():
    retriever=PolicyRetriever()
    response=retriever.search('What is the prerequisite for COMP5926?',method='bm25')
    first=response['results'][0]
    payload=dict(retrieved_evidence_ids=[r['evidence_id'] for r in response['results']],
                 claims=[dict(text='COMP5926 lists COMP5925 Metaverse Project I as a prerequisite.',
                              evidence_id=first['evidence_id'],quote='Pre-requisite: COMP5925 Metaverse Project I')])
    # This is an illustrative draft claim, not an LLM answer-generation call.
    report=verify_claims(payload)
    (ROOT/'data/verifier_demo_input.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'data/verifier_demo_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Integrity gate:',report['status'])
    print('Next: send VERIFIER_INSTRUCTIONS, the claim, canonical evidence and')
    print('retriever.context(evidence_id) to the teammate\'s LLM Verifier.')
    print('No API key or model download was needed for this example.')

if __name__=='__main__': main()
