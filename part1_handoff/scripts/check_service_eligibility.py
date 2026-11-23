"""Regression cases for service identity and student eligibility evidence."""
import json
import os
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from policy_rag.retrieve import PolicyRetriever

def main():
 os.environ.setdefault('HF_HUB_OFFLINE','1')
 retriever=PolicyRetriever();checks=[]
 for method in ['bm25','hybrid']:
  finance=retriever.search('Are part-time students eligible for the PolyU Financial Assistance Scheme?',method=method)
  first=finance['results'][0]
  assert first['citation']['title'].startswith('PolyU Financial Assistance Scheme |')
  assert 'Eligibility: Local full-time government-funded students' in first['text']
  health=retriever.search('Can part-time students use University Health Service?',knowledge_domain='student_services',method=method)
  first=health['results'][0]
  assert re.search(r'UHS service.{0,130}full[ -]time students.{0,40}only',first['text'],re.I)
  assert 'Health and Hygiene |' not in first['citation']['title']
  checks.append(dict(method=method,finance=finance,health=health))
 (ROOT/'data/service_eligibility_checks.json').write_text(json.dumps(dict(status='passed',checks=checks,
  limitation='Checks that eligibility clauses are retrieved; does not decide personal eligibility or generalise a clinic-specific rule to every service.'),ensure_ascii=False,indent=2),encoding='utf-8')
 print('Service eligibility evidence checks PASSED for BM25 and hybrid; semantic/scope review still required.')
if __name__=='__main__':main()
