"""Save a small reproducible retrieval demonstration for manual evidence review."""
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from policy_rag.retrieve import PolicyRetriever
from policy_rag.directory import list_programmes

def main():
 os.environ.setdefault('HF_HUB_OFFLINE','1')
 r=PolicyRetriever()
 cases=[
  ('transcript','If my subject withdrawal is approved in 2025/26, will it still appear on my transcript?',{}),
  ('january_fee','What is the tuition fee for Metaverse Technology for January 2027 entry?',{}),
  ('september_fee','What is the tuition fee for Metaverse Technology for September 2027 entry?',{}),
  ('financial_assistance','Are part-time students eligible for the PolyU Financial Assistance Scheme?',{}),
  ('health_service','Can part-time students use University Health Service?',dict(knowledge_domain='student_services')),
  ('missing_year','What were the graduation credits for programme 61038 in 2020/21?',{}),
 ]
 reports=[]
 for name,question,params in cases:
  result=r.search(question,method='hybrid',top_k=3,**params)
  reports.append(dict(name=name,retrieval=result))
  print(json.dumps(dict(name=name,query=question,status=result['status'],year_filters=result['year_filters'],
   first_results=[dict(text=x['text'][:2600],citation=x['citation'],entry_term=x['entry_term']) for x in result['results'][:2]]),ensure_ascii=False),flush=True)
 report=dict(kind='manual_review_demo_not_independent_accuracy_benchmark',queries=reports,
  directory_counts=dict(jupas=list_programmes(student_type='undergraduate',admission_pathway='jupas')['count'],
                        january_postgraduate=list_programmes(student_type='taught_postgraduate',entry_term='January')['count']))
 path=ROOT/'data/schoolwide_demo_round.json'
 path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Saved',path)

if __name__=='__main__':main()
