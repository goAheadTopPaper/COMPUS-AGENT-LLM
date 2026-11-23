"""Recheck undated original downloads against their current public sources.

Historical annual handbooks remain historical. Byte/clean-text matches are
reported separately from URL availability; neither alone establishes eligibility.
"""
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from policy_rag.prepare import html_records
from download_year_sources import request, stamp

OUT=ROOT/'files/currency_check'

def compare(row):
 result=dict(source_id=row['source_id'],source_url=row['source_url'],checked_at=stamp(),status='failed')
 try:
  data,final,_=request(row['source_url'])
  if any(x in final.lower() for x in ['/signin','/login','/intranet/']): raise ValueError('Authentication destination excluded')
  path=OUT/(row['source_id']+'.'+row['file_type'])
  path.write_bytes(data)
  digest=hashlib.sha256(data).hexdigest()
  result.update(source_url=final,file_path=path.relative_to(ROOT).as_posix(),sha256=digest)
  if row['file_type']=='pdf':
   result['status']='same_pdf_bytes' if digest==row['sha256'] else 'pdf_changed_review_required'
  else:
   fresh=html_records(row,path)[0]['text']
   old=html_records(row,ROOT/row['file_path'])[0]['text']
   canon=lambda text: re.sub(r'\s+',' ',text).strip()
   result['status']='same_clean_text' if canon(fresh)==canon(old) else 'clean_text_changed_review_required'
   if result['status']!='same_clean_text':
    path.with_suffix('.comparison.json').write_text(json.dumps(dict(previous=old,current=fresh),ensure_ascii=False,indent=2),encoding='utf-8')
 except Exception as exc: result['error']=str(exc)
 print(result['source_id'],result['status'],flush=True)
 return result

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 with (ROOT/'data/sources.csv').open(encoding='utf-8-sig',newline='') as f: sources=list(csv.DictReader(f))
 targets=[r for r in sources if not r['captured_at']]
 with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(compare,targets))
 (ROOT/'data/source_currency_checks.json').write_text(json.dumps(dict(checked_at=stamp(),results=results,
   limitation='Only previously unconfirmed original downloads are re-fetched here. Other sources retain their recorded capture dates. A current URL does not prove that every statement on the page is current.'),ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
