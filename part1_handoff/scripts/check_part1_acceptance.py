"""Passage-level development evaluation and full local corpus integrity audit.

Expectations were reviewed against saved source passages. These cases were also
used for fixes, so the report is a regression evaluation, not a held-out benchmark.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from diagnose_part1 import CASES
from policy_rag.retrieve import PolicyRetriever

# Each tuple of patterns must occur together within ONE cited passage. Multiple
# tuples mean that ALL requested evidence facets must be found in the result set.
EXPECTATIONS={
 'leave':[(r'Leave of Absence',r'Form AR8',r'Head of Department')],
 'defer':[(r'Deferment of Study',r'approval|apply|application')],
 'probation':[(r'Academic Probation',r'below 1\.70')],
 'appeal':[(r'Appeals against Decisions on Subject Results',r'within one calendar week')],
 'late_exam':[(r'Late Assessment',r'five working days',r'medical certificate')],
 'retake':[(r'only retake a subject which they have failed',)],
 'credit_transfer':[(r'Application for Credit Transfer',r'AR41c',r'eStudent')],
 'fee_late':[(r'Non-payment of Fees',r'remov|nullif|terminat')],
 'withdraw':[(r'Withdrawal of Subjects',r'apply to your programme',r'justifications')],
 'plagiarism':[(r'Plagiarism refers to',r'acknowledgement')],
 'jupas':[(r'CREDIT REQUIRED',r'120 academic credits',r'3 training credits')],
 'fee_duration':[(r'Tuition Fee',r'13,800'),(r'DURATION',r'year')],
 'credit_prereq':[(r'Credit Value 3',r'COMP5925')],
 'prd':[(r'Application for Graduation',r'credits?')],
 'it':[(r'M201',r'2766\s*5900')],
 'library':[(r'Postgraduate Students',r'Books',r'60')],
 'uhs':[(r'UHS service',r'full[ -]?time students',r'only')],
 'counselling':[(r'counsell',r'stud\.counselling@polyu\.edu\.hk',r'POSS')],
 'missing_year':[], 'missing_programme':[],
}

def evaluate(row):
 result=row['result'];results=result['results'];expected=EXPECTATIONS[row['id']]
 facets=[]
 for patterns in expected:
  ranks=[i+1 for i,x in enumerate(results) if all(re.search(p,' '.join(x['text'].split()),re.I) for p in patterns)]
  facets.append(dict(patterns=patterns,rank=min(ranks) if ranks else None))
 # Empty-evidence cases are evaluated separately, not added to retrieval Hit@k.
 passed=all(x['rank'] is not None for x in facets) if expected else not results
 return dict(id=row['id'],query=row['query'],passed=passed,facets=facets,
             all_facets_at_1=bool(expected) and all(x['rank']==1 for x in facets),
             all_facets_at_5=bool(expected) and passed,
             citations=[x['citation'] for x in results],status=result['status'])

def summarize(rows):
 evaluated=[evaluate(row) for row in rows]
 positive=[x for x in evaluated if x['facets']]
 return dict(cases=len(evaluated),answerable_cases=len(positive),
  all_facets_at_1=sum(x['all_facets_at_1'] for x in positive),
  all_facets_at_5=sum(x['all_facets_at_5'] for x in positive),
  empty_evidence_cases_passed=sum(x['passed'] for x in evaluated if not x['facets']),
  cases_detail=evaluated)

def integrity(r):
 sources=list(csv.DictReader((ROOT/'data/sources.csv').open(encoding='utf-8-sig')))
 chunks=[json.loads(x) for x in (ROOT/'data/chunks.jsonl').read_text(encoding='utf-8').splitlines()]
 by_id={c['chunk_id']:c for c in chunks}
 assert len(by_id)==len(chunks)==len(r.records),'Index/chunk count or uniqueness mismatch'
 assert {s['source_id'] for s in sources}=={c['source_id'] for c in chunks}
 for s in sources:
  assert hashlib.sha256((ROOT/s['file_path']).read_bytes()).hexdigest()==s['sha256'],s['file_path']
 for c,_,_,dense in r.records:
  assert c==by_id[c['chunk_id']],'Stale index payload: '+c['chunk_id']
  assert dense and len(dense)==384,'Missing/wrong embedding dimension'
  assert c['citation']['source_url']==c['source_url']
  if c['source_type']=='handbook':
   assert not re.search(r'^1\. (Announcements|For non-local)',c['citation']['section']),c['citation']
 return dict(status='passed',sources_hashed=len(sources),passages_checked=len(chunks),embedding_dimension=384)

def main():
 os.environ.setdefault('HF_HUB_OFFLINE','1')
 r=PolicyRetriever();after=[]
 for name,query,params in CASES:
  after.append(dict(id=name,query=query,result=r.search(query,method='hybrid',**params)))
 (ROOT/'data/part1_probe_after.json').write_text(json.dumps(after,ensure_ascii=False,indent=2),encoding='utf-8')
 before=json.loads((ROOT/'data/part1_probe_before.json').read_text(encoding='utf-8'))
 report=dict(dataset_type='assistant_reviewed_development_regression_not_held_out',
  scope='Part 1: source integrity, passage retrieval, filters and evidence metadata; no generated-answer or agent evaluation',
  before=summarize(before),after=summarize(after),integrity=integrity(r))
 # Check metadata as well as passage text; a plausible passage under the wrong
 # programme type/year is not a successful handoff.
 lookup={row['id']:row['result'] for row in after}
 assert lookup['jupas']['preferred_page_type']=='ProgrammeDetails'
 assert all(x['admission_pathway']=='jupas' and x['programme_code']=='JS3060' for x in lookup['jupas']['results'])
 assert lookup['uhs']['knowledge_domain']=='student_services'
 assert lookup['plagiarism']['results'][0]['citation']['section'].startswith('Appendix 2. Plagiarism')
 assert all(x['entry_term']=='September' and x['academic_year']=='2027/28' for x in lookup['fee_duration']['results'])
 for row in after:
  year=re.search(r'20\d{2}/\d{2}',row['query'])
  if year:assert all(x['academic_year']==year.group() for x in row['result']['results'])
 conflicts=[dict(entry_term='September'),dict(entry_year=2028)]
 for params in conflicts:
  try:
   r.search('Tuition fee for Metaverse Technology January 2027 entry',method='bm25',**params)
  except ValueError as error:
   assert 'conflicts' in str(error)
  else:
   raise AssertionError('Contradictory entry filter was silently accepted')
 report['conflicting_entry_filters']='rejected'
 (ROOT/'data/part1_acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# Part 1 retrieval test report', '',
  'Scope: collection, source provenance, vector index, retrieval and the evidence interface.',
  'No agent, generated-answer, frontend or live school API work is graded here.', '',
  'These 20 questions were used for diagnosis and fixes. The expectations were checked against saved passages. This is a development regression evaluation, not an independent benchmark.', '',
  '| Measure | Before | After |', '|---|---:|---:|']
 for key,label in [('all_facets_at_1','All requested evidence in first passage (18 questions)'),('all_facets_at_5','All requested evidence within top 5 (18 questions)'),('empty_evidence_cases_passed','Unsupported year/programme returns no evidence (2 questions)')]:
  lines.append(f"| {label} | {report['before'][key]} | {report['after'][key]} |")
 lines+=['','The fee-and-duration question requires two passages; a single first passage is not expected to cover it.', '',
  '| Question | Before supporting ranks | After supporting ranks |', '|---|---|---|']
 for b,a in zip(report['before']['cases_detail'],report['after']['cases_detail']):
  def ranks(x):return ', '.join(str(f['rank']) if f['rank'] else 'missing' for f in x['facets']) or ('correctly empty' if x['passed'] else 'unexpected evidence')
  lines.append(f"| {a['query']} | {ranks(b)} | {ranks(a)} |")
 lines+=['', '## Integrity and integration', '',
  f"- Verified SHA-256 of all {report['integrity']['sources_hashed']} active original files against the source catalogue.",
  f"- Matched all {report['integrity']['passages_checked']:,} index payloads to generated chunks; checked unique IDs, citations and 384-dimensional embeddings.",
  '- Checked strict academic years, JUPAS programme/pathway identity, UHS routing, corrected appendix citations and rejection of conflicting entry filters.',
  '- Source hashes confirm local consistency, not a new live website freshness check.',
  '- Scores are retrieval ranks, not confidence or proof of answer correctness. Existing source/date/scope warnings are retained.', '',
  '## Reproduce', '', 'Run from the project folder:', '', '```powershell',
  'python -X utf8 scripts/check_part1_acceptance.py', '```', '',
  'Full evidence: data/part1_probe_before.json and data/part1_probe_after.json. Machine-readable results: data/part1_acceptance.json.',
  'The before snapshot is retained as the original baseline. Do not overwrite it when rerunning tests.']
 (ROOT/'data/part1_test_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 for phase in ['before','after']:
  s=report[phase]
  print(f"{phase}: complete evidence at rank 1 {s['all_facets_at_1']}/{s['answerable_cases']}; within top 5 {s['all_facets_at_5']}/{s['answerable_cases']}; empty cases {s['empty_evidence_cases_passed']}/2")
 failures=[x['id'] for x in report['after']['cases_detail'] if not x['passed']]
 print('Full local source/index integrity:',report['integrity'])
 assert not failures, 'Evidence gaps: '+', '.join(failures)
 print('Part 1 acceptance checks PASSED. These are development results, not general answer accuracy.')

if __name__=='__main__':main()
