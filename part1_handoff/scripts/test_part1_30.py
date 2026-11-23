"""Thirty reproducible Part 1 questions: 20 regression and 10 new variants."""
import csv
import json
import os
from pathlib import Path
import re
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from diagnose_part1 import CASES
from check_part1_acceptance import EXPECTATIONS
from policy_rag.retrieve import PolicyRetriever

EXTRA=[
 ('withdraw_2024','For 2024/25, what approvals are needed to withdraw from a subject?',{},[(r'Withdrawal of Subjects',r'Subject Teacher',r'Programme Leader')]),
 ('withdraw_refund','For 2026/27, are tuition fees refunded after an approved subject withdrawal?',{},[(r'Withdrawal of Subjects',r'not be refunded')]),
 ('withdraw_record','Does an approved subject withdrawal appear on my transcript in 2025/26?',{},[(r'Withdrawal of Subjects',r'transcript of studies')]),
 ('withdraw_deadline','In 2024/25, can I request subject withdrawal after examinations have started?',{},[(r'Withdrawal of Subjects',r'commencement of the examination period')]),
 ('probation_2026','What GPA triggers academic probation in 2026/27?',{},[(r'Academic Probation',r'below 1\.70')]),
 ('jan_fee','How much is tuition for Metaverse Technology January 2027 entry?',{},[(r'Tuition Fee',r'13,100')]),
 ('subject_credit','What is the credit value of COMP5584?',{},[(r'COMP5584',r'Credit Value 3')]),
 ('subject_prereq','Which subject must I complete before COMP5926?',{},[(r'Pre-requisite: COMP5925')]),
 ('unknown_policy_year','What are the withdrawal rules for subjects in 2022/23?',{},[]),
 ('unknown_subject_year','What is the prerequisite of COMP5926 in 2020/21?',{},[]),
]

def main():
 os.environ.setdefault('HF_HUB_OFFLINE','1')
 r=PolicyRetriever();rows=[]
 tests=[(name,q,p,EXPECTATIONS[name]) for name,q,p in CASES]+EXTRA
 for i,(name,q,params,expected) in enumerate(tests,1):
  start=time.perf_counter();response=r.search(q,method='hybrid',top_k=5,**params)
  facets=[]
  for patterns in expected:
   ranks=[rank for rank,x in enumerate(response['results'],1) if all(re.search(pattern,' '.join(x['text'].split()),re.I) for pattern in patterns)]
   facets.append(min(ranks) if ranks else None)
  passed=all(rank is not None for rank in facets) if expected else not response['results']
  # Explicit years must also match every returned passage.
  year=re.search(r'20\d{2}/\d{2}',q)
  scope_ok=not year or all(x['academic_year']==year.group() for x in response['results'])
  passed=bool(passed and scope_ok)
  row=dict(number=i,id=name,query=q,case_type='previous_regression' if i<=20 else 'new_variant',
   passed=passed,expected_patterns=expected,evidence_ranks=facets,scope_ok=bool(scope_ok),
   milliseconds=round((time.perf_counter()-start)*1000,1),response=response)
  rows.append(row);print(f'{i:02} {"PASS" if passed else "FAIL"} {name}: {facets}',flush=True)
 positives=[x for x in rows if x['expected_patterns']]
 summary=dict(total=30,passed=sum(x['passed'] for x in rows),failed=sum(not x['passed'] for x in rows),
  answerable=len(positives),complete_evidence_at_1=sum(all(rank==1 for rank in x['evidence_ranks']) for x in positives),
  complete_evidence_at_5=sum(x['passed'] for x in positives),unsupported_cases=30-len(positives),
  unsupported_correctly_empty=sum(x['passed'] for x in rows if not x['expected_patterns']))
 report=dict(scope='Part 1 retrieval and evidence only',dataset_type='20 previous development cases plus 10 new variants; not independently labelled or held out',summary=summary,cases=rows)
 (ROOT/'data/part1_30_tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 with (ROOT/'data/part1_30_tests.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.writer(f);writer.writerow(['number','question','case_type','result','supporting_ranks','first_source_url'])
  for x in rows:writer.writerow([x['number'],x['query'],x['case_type'],'PASS' if x['passed'] else 'FAIL',str(x['evidence_ranks']),next(iter(x['response']['results']),{}).get('citation',{}).get('source_url','')])
 lines=['# Part 1: 30-question test record','',json.dumps(summary,indent=2),'',
  '20 previous regression questions and 10 new variants. Tests check retrieved passages and explicit academic-year isolation. They do not measure generated answers or independent accuracy.','',
  '| # | Question | Result | Supporting ranks |','|---|---|---|---|']
 for x in rows:lines.append(f"| {x['number']} | {x['query']} | {'PASS' if x['passed'] else 'FAIL'} | {x['evidence_ranks']} |")
 lines+=['','Empty ranks on unsupported cases mean that no evidence was returned, as expected. Full passages, citations and expectations are saved in part1_30_tests.json.',
  'Reproduce: `python -X utf8 scripts/test_part1_30.py`']
 (ROOT/'data/part1_30_tests.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
