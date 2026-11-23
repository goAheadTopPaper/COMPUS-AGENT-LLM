"""Measure catalogue-link coverage and check programme/service retrieval."""
from collections import Counter
import csv
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from urllib.parse import urlparse,parse_qsl,urlunparse
from policy_rag.retrieve import PolicyRetriever
from policy_rag.directory import list_programmes

def canonical(url):
 p=urlparse(url)
 return urlunparse((p.scheme,p.netloc,p.path.rstrip('/'),'','&'.join(f'{k}={v}' for k,v in parse_qsl(p.query) if k!='sc_lang'),''))

def main():
 os.environ.setdefault('HF_HUB_OFFLINE','1')
 rows=json.loads((ROOT/'files/schoolwide/download_manifest.json').read_text(encoding='utf-8'))
 with (ROOT/'data/sources.csv').open(encoding='utf-8-sig',newline='') as f:sources=list(csv.DictReader(f))
 indexed={canonical(x['source_url']):x for x in sources}
 programme_rows=[x for x in rows if x['source_type']=='programme_information']
 assert programme_rows and all(canonical(x.get('source_url',x['requested_url'])) in indexed for x in programme_rows), 'A discovered programme detail is not indexed'
 assert list_programmes()['count']==len(programme_rows),'Structured catalogue listing is incomplete'
 pathway_counts=Counter(indexed[canonical(x.get('source_url',x['requested_url']))].get('admission_pathway') or 'taught_postgraduate' for x in programme_rows)
 discovery=json.loads((ROOT/'files/schoolwide/discovery.json').read_text(encoding='utf-8'))
 # Every pagination link must have been fetched, including the final page.
 seen={canonical(x['source_url']) for x in discovery if x['status']=='downloaded'}
 for page in discovery:
  if page['name'].startswith('ug'):
   for link in page.get('links',[]):
    if 'page=' in link['url']:assert canonical(link['url']) in seen,'Unfollowed undergraduate catalogue page'
 retriever=PolicyRetriever()
 cases=[]
 for query,params in [
  ('What is the curriculum of JS3060?',dict(programme_code='JS3060',entry_year=2027,entry_term='September',admission_pathway='jupas')),
  ('How many credits are required for programme 61038 for January 2027 entry?',{}),
  ('How many credits are required for programme 61038 for September 2027 entry?',{}),
  ('What is the PolyU Emergency Financial Assistance Scheme?',{}),
  ('Where can I find support for students with special needs?',dict(knowledge_domain='student_services')),
  ('What PhD and MPhil research programmes are available?',{}),
 ]:
  result=retriever.search(query,method='hybrid',**params)
  assert result['results'],query
  if 'JS3060' in query:
   assert all(x['programme_code']=='JS3060' and x['admission_pathway']=='jupas' for x in result['results'])
  if 'January' in query:
   assert all(x['entry_term']=='January' and x['academic_year']=='2026/27' for x in result['results'])
  if 'September' in query:
   assert all(x['entry_term']=='September' and x['academic_year']=='2027/28' for x in result['results'])
  if 'Financial' in query or 'special needs' in query:assert result['knowledge_domain']=='student_services'
  if 'PhD' in query:assert result['knowledge_domain']=='academic_information' and all(x['page_type']=='ResearchProgrammes' for x in result['results'])
  cases.append(result)
 ambiguous=retriever.search('How many credits are required for programme 61038 for 2027 entry?',method='bm25')
 assert ambiguous['requires_entry_term_clarification'],'January and September ambiguity not exposed'
 report=dict(status='passed',catalogue_programme_detail_urls=len(programme_rows),indexed_programme_detail_urls=len(programme_rows),
             undergraduate_pathways=dict(pathway_counts),
             distinct_undergraduate_codes=len({x['programme'] for x in sources if x['source_type']=='programme_information' and x['student_type']=='undergraduate'}),
             postgraduate_entry_counts=dict(Counter(x['entry_term']+' '+x['entry_year'] for x in sources if x['source_type']=='programme_information' and x['student_type']=='taught_postgraduate')),
             service_sources=sum(x['source_type']=='student_service' for x in sources),
             research_link_outcomes=dict(Counter(x['status'] for x in rows if x['source_type']=='research_programme_information')),
             unavailable_links=[dict(url=x['requested_url'],kind=x['source_type'],reason=x.get('error','')) for x in rows if x['status']=='failed'],
             checks=cases,limitation='Coverage of saved central catalogues and linked public services. Not every historical programme, PRD, specialism or service document. Research units do not have uniform catalogue identifiers.')
 (ROOT/'data/schoolwide_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print('School-wide checks PASSED:',len(programme_rows),'catalogue programme URLs indexed; pathway/term isolation; service/research routing.')

if __name__=='__main__':main()
