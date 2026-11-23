"""Collect a bounded set of public PRDs, subject forms and service guidance.

Only official public links are used. No sign-in, intranet crawling or access-control
bypass. Undated subject forms/service pages are never assigned an academic year.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import re
import time
from urllib.parse import urlparse, unquote
from pathlib import Path
from lxml import html
from pypdf import PdfReader
from download_year_sources import request, stamp

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'files/extended_resources'
SERVICES={
 'SAO services and support':'https://www.polyu.edu.hk/sao/',
 'SAO contact and service enquiries':'https://www.polyu.edu.hk/en/sao/about-sao/contact-us/',
 'Scholarship types and eligibility':'https://www.polyu.edu.hk/sao/student-resources-and-support-section/scholarships/scholarship-types/?sc_lang=en',
 'Undergraduate hall admission policies':'https://www.polyu.edu.hk/sao/student-resources-and-support-section/residential-life/hall-admission/admission-policies-undergraduates/?sc_lang=en',
 'University Health Service appointment guidance':'https://www.polyu.edu.hk/uhs/make-an-appointment/?sc_lang=en',
 'Campus clinics and locations':'https://www.polyu.edu.hk/cfso/campus-environment-and-facilities/clinics/?sc_lang=en',
 'IT services for new students':'https://www.polyu.edu.hk/its/students/it-services-for-new-students/?sc_lang=en',
 'IT HelpCentre contact and service hours':'https://www.polyu.edu.hk/its/about-its/contact-us/?sc_lang=en',
 'New Student Orientation useful information':'https://www.polyu.edu.hk/nso/useful-information/',
 'Library loan privileges':'https://www.lib.polyu.edu.hk/services/borrowing/loan-privileges',
 'Library opening hours':'https://www.lib.polyu.edu.hk/about-us/hours',
 'Library regulations':'https://www.lib.polyu.edu.hk/about-us/library/regulations/library-regulations',
}
UNITS={
 'eee_prds':('Faculty of Engineering','Department of Electrical and Electronic Engineering'),
 'aae_prds':('Faculty of Engineering','Department of Aeronautical and Aviation Engineering'),
 'me_students':('Faculty of Engineering','Department of Mechanical Engineering'),
 'science_prds':('Faculty of Science','Faculty of Science'),
 'fb_bm_resources':('Faculty of Business','Faculty of Business'),
}

def tasks():
 discovery=json.loads((OUT/'discovery.json').read_text(encoding='utf-8'))
 rows=[]
 for index in discovery:
  name=index['name']
  if index['status']!='downloaded': continue
  if name.startswith('comp_mt_') or name=='dsai_aibd_curriculum':
   faculty='Faculty of Computer and Mathematical Sciences'
   unit='Department of Computing' if name.startswith('comp') else 'Department of Data Science and Artificial Intelligence'
   rows.append(dict(requested_url=index['source_url'],title=name.replace('_',' '),source_type='programme_guidance',
                    programme_code='61038' if name.startswith('comp_mt_') else '62037',faculty=faculty,unit=unit,
                    academic_year='not_specified',year_basis='not_explicitly_versioned',discovered_from=index['source_url']))
  for a in index.get('links',[]):
   url=a['url']
   if '/intranet/' in url: continue
   code=re.search(r'/subject/(COMP\d{4,5}[A-Z]?)\.pdf',url,re.I)
   if name=='comp_mt_subjects' and code:
    rows.append(dict(requested_url=url,title=a['label'] or code.group(1),source_type='subject_description',
                     subject_code=code.group(1).upper(),faculty='Faculty of Computer and Mathematical Sciences',unit='Department of Computing',
                     programme_code='not_programme_specific',academic_year='not_specified',year_basis='undated_public_subject_form',discovered_from=index['source_url']))
   elif name in UNITS and ('.pdf' in url.lower() or 'fbweb.polyu.edu.hk/rpss/dpd/' in url) and re.search(r'2026[/\-]27|202627|year=2627',a['label']+' '+url):
    # Academic calendar/annual university handbook are already separately indexed.
    if '/ar/docdrive/' in url or 'brochure' in url.lower(): continue
    faculty,unit=UNITS[name]
    code_match=re.search(r'(?<!\d)(\d{5})(?!\d)',unquote(urlparse(url).path))
    if not code_match: code_match=re.search(r'code=(\d{5})',url)
    if not code_match:
     # Skip research-wide documents that cannot safely map to one programme.
     continue
    code_value=code_match.group(1)
    rows.append(dict(requested_url=url,title=(a['context'] if name=='me_students' else a['heading']) or a['label'],
                     source_type='programme_requirements',programme_code=code_value,faculty=faculty,unit=unit,
                     academic_year='2026/27',year_basis='official_2026_27_document_link_and_pdf_text',discovered_from=index['source_url']))
 # An additional official Business PRD found through official search results.
 rows.append(dict(requested_url='https://www.polyu.edu.hk/af/-/media/department/af/content/study/ug/bachelor-of-business-administration-honours-in-accounting-and-finance/program-booklet/202627/21453-prdbba-scheme-in-af-20262720261028.pdf?hash=B0F21F87591BBC3779332C33DD4172C2&rev=0657d3468d9e4341bf3cd161e4acfffd',
                  title='BBA Scheme in Accounting and Finance PRD 2026/27',source_type='programme_requirements',programme_code='21453',
                  faculty='Faculty of Business',unit='School of Accounting and Finance',academic_year='2026/27',
                  year_basis='official_2026_27_document_link_and_pdf_text',discovered_from='official PolyU search result'))
 for title,url in SERVICES.items():
  rows.append(dict(requested_url=url,title=title,source_type='student_service',programme_code='not_programme_specific',faculty='',unit='',
                   academic_year='not_specified',year_basis='undated_service_snapshot',discovered_from='official PolyU service page'))
 # Deduplicate the same link repeated in navigation, preserving meaningful labels.
 return list({r['requested_url']:r for r in rows}.values())

def download(row):
 row=dict(row,status='failed')
 try:
  raw,final,ctype=request(row['requested_url'])
  if any(x in final.lower() for x in ['/login','/intranet/','/signin']): raise ValueError('Sign-in/intranet destination excluded')
  pdf=raw.startswith(b'%PDF')
  if pdf:
   reader=PdfReader(io.BytesIO(raw))
   if reader.is_encrypted: raise ValueError('Encrypted PDF excluded')
   preview='\n'.join(p.extract_text() or '' for p in reader.pages[:10])
   all_text=preview+'\n'+'\n'.join(p.extract_text() or '' for p in reader.pages[10:])
   if len(all_text.strip())<150: raise ValueError('Scanned/empty PDF requires OCR review')
   identity_text=re.sub(r'\s','',all_text).replace('–','-').replace('−','-').replace('—','-')
   if row['source_type']=='programme_requirements':
    if not re.search(r'2026[/\-](?:20)?27|2026/2027',identity_text): raise ValueError('2026/27 version not confirmed in PDF text')
    if row['programme_code'] not in identity_text: raise ValueError('Programme code not confirmed in PDF text')
   if row['source_type']=='subject_description' and row['subject_code'].upper() not in identity_text.upper():
    raise ValueError('Subject code not confirmed in PDF text')
   row['pages']=len(reader.pages)
  else:
   if 'html' not in ctype: raise ValueError('Expected public HTML or PDF')
   tree=html.fromstring(raw)
   preview=' '.join(tree.text_content().split())
   if re.search(r'access denied|request rejected|sign in to your account',preview,re.I): raise ValueError('Access-control page excluded')
   title=' '.join(tree.xpath('//title/text()')).strip()
   if title: row['title']=title
   if row['source_type']=='programme_requirements': raise ValueError('PRD link returned HTML, not a verified PDF; requires manual review')
  suffix='.pdf' if pdf else '.html'
  group={'programme_requirements':'programme_requirements','subject_description':'subject_descriptions','student_service':'student_services','programme_guidance':'programme_guidance'}[row['source_type']]
  slug=row.get('subject_code') or (row['programme_code'] if row['programme_code']!='not_programme_specific' else re.sub('[^a-z0-9]+','_',row['title'].lower())[:65])
  path=OUT/group/(slug+'_'+hashlib.sha256(final.encode()).hexdigest()[:10]+suffix)
  path.parent.mkdir(parents=True,exist_ok=True)
  path.write_bytes(raw)
  path.with_suffix('.preview.txt').write_text(preview[:12000],encoding='utf-8')
  row.update(status='downloaded',source_url=final,file_path=path.relative_to(ROOT).as_posix(),file_type=suffix[1:],
             captured_at=stamp(),sha256=hashlib.sha256(raw).hexdigest(),
             notes='Public source snapshot. Read exact intake and student-group conditions; neither document version nor capture date establishes individual eligibility or live subject availability.')
  if row['source_type']=='programme_requirements':
   row['title']='Programme '+row['programme_code']+' — PRD 2026/27 — '+row['title']
  row['student_type']='undergraduate' if row['programme_code'] in {'01402','21453','46408','46409','43499'} else ('taught_postgraduate' if row['source_type']=='programme_requirements' else 'mixed')
  if row['source_type']=='subject_description': row['student_type']='taught_postgraduate'
 except Exception as exc:
  row['error']=str(exc)
 print(row['source_type'],row.get('subject_code') or row['programme_code'],row['status'],row.get('error',''),flush=True)
 time.sleep(.3)
 return row

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 manifest=OUT/'download_manifest.json'
 old={r['requested_url']:r for r in json.loads(manifest.read_text(encoding='utf-8'))} if manifest.exists() else {}
 for row in old.values():
  if row['requested_url']=='https://www.lib.polyu.edu.hk/about/handbook/LibHBstudent_eng.pdf':
   row.update(status='archived_outdated',academic_year='2012/13',year_basis='explicit_cover_year',
              notes='Cover explicitly says 2012/13. Preserve original for audit but exclude from active retrieval; replaced by public Library web guidance.')
 items=tasks()
 todo=[r for r in items if not (r['requested_url'] in old and old[r['requested_url']]['status']=='downloaded')]
 with ThreadPoolExecutor(max_workers=3) as pool:
  for row in pool.map(download,todo):
   old[row['requested_url']]=row
   manifest.write_text(json.dumps(list(old.values()),ensure_ascii=False,indent=2),encoding='utf-8')
 for row in old.values():
  if row['status']=='downloaded' and row['source_type']=='programme_requirements':
   row['student_type']='undergraduate' if row['programme_code'] in {'01402','21453','46408','46409','43499'} else 'taught_postgraduate'
 manifest.write_text(json.dumps(list(old.values()),ensure_ascii=False,indent=2),encoding='utf-8')
 print('Manifest:',manifest,flush=True)

if __name__=='__main__': main()
