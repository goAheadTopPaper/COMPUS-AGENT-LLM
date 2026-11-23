"""Save fresh development probes; no LLM answer generation or external calls."""
import json
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from policy_rag.retrieve import PolicyRetriever

CASES = [
 ('leave', 'How do I request leave of absence for a few days in 2026/27?', {}),
 ('defer', 'Can I pause my studies for a semester in 2026/27?', {}),
 ('probation', 'When will I be put on academic probation in 2025/26?', {}),
 ('appeal', 'How long do I have to appeal my assessment results in 2026/27?', {}),
 ('late_exam', 'What should I do if illness prevents me from attending an examination in 2026/27?', {}),
 ('retake', 'In 2026/27, can I retake a subject I have already passed to improve my grade?', {}),
 ('credit_transfer', 'How do I apply for credit transfer in 2026/27?', {}),
 ('fee_late', 'What happens if I do not pay tuition fees on time in 2026/27?', {}),
 ('withdraw', 'If I stop attending one module after add/drop in 2025/26, is that enough to withdraw?', {}),
 ('plagiarism', 'What counts as plagiarism in 2026/27?', {}),
 ('jupas', 'How many credits are required for JUPAS JS3060 for September 2027 entry?', {}),
 ('fee_duration', 'For Metaverse Technology September 2027 entry, what are the tuition fee and normal study duration?', {}),
 ('credit_prereq', 'What are the credit value and prerequisites for COMP5926?', {}),
 ('prd', 'What are the graduation credit requirements for programme 46010 in 2026/27?', {}),
 ('it', 'Where is the IT HelpCentre and how can I contact it?', {}),
 ('library', 'How many library books may a taught postgraduate student borrow?', {}),
 ('uhs', 'Can part-time students use UHS?', {}),
 ('counselling', 'How do I book an appointment for counselling?', {}),
 ('missing_year', 'What are the subject withdrawal rules in 2020/21?', {}),
 ('missing_programme', 'What are the graduation credits for programme 99999 in 2026/27?', {}),
]

def main():
 target = ROOT/'data'/('part1_probe_' + (sys.argv[1] if len(sys.argv)>1 else 'latest') + '.json')
 if target.name=='part1_probe_before.json' and target.exists():
  raise SystemExit('The original before baseline already exists. Use a different run name.')
 os.environ.setdefault('HF_HUB_OFFLINE', '1')
 r = PolicyRetriever()
 rows = []
 for name, query, params in CASES:
  result = r.search(query, method='hybrid', **params)
  rows.append(dict(id=name, query=query, result=result))
  print(json.dumps(dict(id=name, domain=result['knowledge_domain'], status=result['status'],
   results=[dict(id=x['evidence_id'], section=x['citation']['section'], title=x['citation']['title'], text=x['text'][:1700]) for x in result['results'][:3]]), ensure_ascii=False), flush=True)
 target.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__': main()
