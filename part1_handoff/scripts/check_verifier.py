"""Check rejection of forged citations, altered sources and scope mismatches."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from policy_rag.retrieve import PolicyRetriever
from policy_rag.verify import verify_claims

def main():
    r=PolicyRetriever()
    c=r.search('What is the prerequisite for COMP5926?',method='bm25')['results'][0]
    good=dict(claims=[dict(text='COMP5926 requires COMP5925.',evidence_id=c['evidence_id'],quote='Pre-requisite: COMP5925 Metaverse Project I')],retrieved_evidence_ids=[c['evidence_id']])
    assert verify_claims(good)['status']=='pending_semantic_review'
    cases={}
    for name,field,value in [('forged_id','evidence_id','invented-id'),('fabricated_quote','quote','No prerequisites are required.'),('altered_citation','citation',{'pdf_page':999})]:
        bad=deepcopy(good); bad['claims'][0][field]=value
        result=verify_claims(bad); assert result['status']=='rejected'; cases[name]=result['status']
    bad=deepcopy(good); bad['retrieved_evidence_ids']=[]
    assert verify_claims(bad)['status']=='rejected'; cases['not_retrieved']='rejected'
    bad=deepcopy(good); bad['academic_year']='2026/27'
    assert verify_claims(bad)['status']=='rejected'; cases['undated_form_for_explicit_year']='rejected'
    # A real quotation attached to a contradictory claim must NEVER auto-approve.
    bad=deepcopy(good); bad['claims'][0]['text']='COMP5926 has no prerequisite.'
    result=verify_claims(bad); assert not result['approved'] and result['status']=='pending_semantic_review'
    cases['semantic_contradiction_not_auto_approved']=result['status']
    prd=r.search('Graduation credits for programme 46010 in 2026/27',method='bm25')['results'][0]
    scope=dict(academic_year='2025/26',programme_code='46012',claims=[dict(text='Graduation requirement.',evidence_id=prd['evidence_id'],quote=prd['text'][:100])])
    result=verify_claims(scope)
    assert 'academic_year_mismatch' in result['claims'][0]['errors'] and 'programme_mismatch' in result['claims'][0]['errors']
    cases['wrong_year_and_programme']='rejected'
    # Test source tampering in a temporary root without modifying original downloads.
    record=next(x for x,_,_,_ in r.records if x['chunk_id']==c['evidence_id'])
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/record['file_path']; path.parent.mkdir(parents=True); path.write_bytes(b'altered source')
        result=verify_claims(good,source_root=temp)
        assert 'original_source_hash_mismatch' in result['claims'][0]['errors']
    cases['tampered_source']='rejected'
    (ROOT/'data/verifier_checks.json').write_text(json.dumps(dict(status='passed',cases=cases),indent=2),encoding='utf-8')
    print('Verifier checks PASSED: 8 negative cases and a valid pending-review case.')

if __name__=='__main__': main()
