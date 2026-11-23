"""Regression checks for provenance, subject identity, PRD years and services."""
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from policy_rag.retrieve import PolicyRetriever

def main():
 os.environ.setdefault('HF_HUB_OFFLINE','1')
 manifest=json.loads((ROOT/'files/extended_resources/download_manifest.json').read_text(encoding='utf-8'))
 chunks=[json.loads(line) for line in (ROOT/'data/chunks.jsonl').read_text(encoding='utf-8').splitlines()]
 paths={c['file_path'] for c in chunks}
 for item in manifest:
  if item['status']=='downloaded':
   assert item['file_path'] in paths
   assert hashlib.sha256((ROOT/item['file_path']).read_bytes()).hexdigest()==item['sha256']
   if item['source_type'] in {'subject_description','student_service'}:
    assert item['academic_year']=='not_specified'
 r=PolicyRetriever()
 reports=[]
 for method in ['bm25','hybrid']:
  subject=r.search('What is the prerequisite for COMP5926?',method=method)
  assert subject['results'] and subject['results'][0]['source_type']=='subject_description'
  assert 'COMP5925' in subject['results'][0]['text']
  assert all('COMP5926' in x['citation']['title'] for x in subject['results'])
  llm=r.search('How many credits is COMP5584?',method=method)
  assert llm['results'] and llm['results'][0]['source_type']=='subject_description'
  assert 'Credit Value 3' in llm['results'][0]['text']
  # No invented 2026/27 date on a public form that is not versioned by year.
  unknown=r.search('What is the prerequisite for COMP5926 in 2026/27?',method=method)
  assert all(x['academic_year']=='2026/27' for x in unknown['results'])
  assert not any(x['source_type']=='subject_description' for x in unknown['results'])
  prd=r.search('What are the graduation credit requirements for programme 46010 in 2026/27?',method=method)
  assert prd['results'] and all(x['source_type']=='programme_requirements' and x['programme_code']=='46010' and x['academic_year']=='2026/27' for x in prd['results'])
  assert prd['programme_requirements_coverage']
  incompatible=r.search('Credit requirements for programme 46010 in 2026/27',student_type='undergraduate',method=method)
  assert not incompatible['results'], 'Known taught-postgraduate PRD leaked into undergraduate filtering'
  wrong=r.search('What are the graduation credit requirements for programme 46010 in 2025/26?',method=method)
  assert not any(x['source_type']=='programme_requirements' for x in wrong['results'])
  services=r.search('Where is the IT HelpCentre?',method=method)
  assert services['knowledge_domain']=='student_services' and services['results']
  assert all(x['source_type']=='student_service' for x in services['results'])
  assert 'M201' in ' '.join(x['text'] for x in services['results'])
  reports.append(dict(method=method,subject=subject,llm_subject=llm,strict_year_subject=unknown,prd=prd,service=services))
 report=dict(status='passed',additional_sources=sum(x['status']=='downloaded' for x in manifest),tests=reports,
             limitation='Development retrieval checks, not an independent answer-quality benchmark or evidence of complete university coverage.')
 (ROOT/'data/extended_resource_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Extended resource checks PASSED: source hashes, all selected sources indexed, subject codes, prerequisites, PRD year isolation and service routing.')

if __name__=='__main__': main()
