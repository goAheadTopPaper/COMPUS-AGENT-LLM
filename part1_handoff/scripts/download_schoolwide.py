"""Collect all discovered public programme cards/details and service navigation.

Coverage is measured against the saved official catalogues, not every historical
programme/PRD. No intranet, login, application-submission or private endpoints.
"""
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlparse,urljoin,parse_qsl,urlencode,urlunparse
from lxml import html
from download_year_sources import request,stamp
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'files/schoolwide'

def canonical(url):
 p=urlparse(url)
 return urlunparse((p.scheme,p.netloc,p.path.rstrip('/'),'','&'.join(f'{k}={v}' for k,v in parse_qsl(p.query) if k!='sc_lang'),''))

def make_tasks():
 discovery=json.loads((OUT/'discovery.json').read_text(encoding='utf-8'))
 rows={}
 def add(url,kind,label,origin,**meta):
  if any(x in url.lower() for x in ['/internal/','/intranet/','/login','/signin','rpgadmission.','/internalsearch','/privacy','/news/','/events/']):return
  if urlparse(url).hostname not in {'www.polyu.edu.hk','www.lib.polyu.edu.hk'}:return
  if re.search(r'\.(?:pdf|jpg|png|zip|docx?|xlsx?)(?:\?|$)',url,re.I):return
  key=canonical(url)
  rows.setdefault(key,dict(requested_url=url,title=label,source_type=kind,discovered_from=origin,
      programme_code='not_programme_specific',academic_year='not_specified',entry_year='',entry_term='',
      faculty='',unit='',student_type='mixed',page_type='StudentService' if kind=='student_service' else 'Programmes',
      year_basis='undated_public_catalogue_or_service_snapshot',**meta))
 for source in discovery:
  if source['status']!='downloaded':continue
  name=source['name']; url=source['source_url']
  kind='student_service' if name in {'services','it_services','health_services','library_services'} else 'programme_directory'
  add(url,kind,name.replace('_',' '),url)
  tree=html.fromstring((ROOT/source['file_path']).read_bytes())
  if name.startswith(('ug','tpg')):
   for a in tree.xpath('//a[contains(concat(" ",normalize-space(@class)," ")," programme ")][@href]'):
    target=urljoin(url,a.get('href')).split('#')[0]
    label=' '.join(a.text_content().split())
    m=re.search(r'/study/(?:ug/([^/]+)/(20\d{2})/([^/?]+)|pg/tpg/(20\d{2,3})/(\d{5}[^/?]*))',target)
    if not m:continue
    add(target,'programme_information',label,url)
    rows[canonical(target)].update(student_type='undergraduate' if name.startswith('ug') else 'taught_postgraduate',
       page_type='ProgrammeDetails',admission_pathway=m[1] or 'taught_postgraduate')
  elif name=='rpg':
   rows[canonical(url)].update(page_type='ResearchProgrammes',student_type='research_postgraduate')
   for a in tree.xpath('//table//a[@href]'):
    target=urljoin(url,a.get('href'));label=' '.join(a.text_content().split())
    if not re.search(r'^(?:Department|School|Division) of ',label):continue
    add(target,'research_programme_information',label,url)
    headings=a.xpath('ancestor::table[1]//h5')
    if canonical(target) in rows:rows[canonical(target)].update(student_type='research_postgraduate',page_type='ResearchProgrammes',unit=label,faculty=' '.join(headings[0].text_content().split()) if headings else '')
  elif name in {'services','it_services','health_services','library_services'}:
   for a in source['links']:
    target=a['url'];path=urlparse(target).path
    relevant=(name=='services' and any(s in path for s in ['/student-resources-and-support-section/','/careers-and-placement-section/','/student-counselling/','/sports-development/'])) or (name=='it_services' and '/its/it-services/' in path) or (name=='health_services' and '/uhs/' in path and not path.endswith('/uhs/')) or (name=='library_services' and '/services/' in path)
    if relevant:add(target,'student_service',a['label'],url)
 return list(rows.values()),discovery

def download(row):
 row=dict(row,status='failed')
 try:
  catalogue_label=row['title']
  raw,final,ctype=request(row['requested_url'])
  if 'html' not in ctype:raise ValueError('Expected public HTML')
  if any(x in final.lower() for x in ['/login','/intranet/','/signin']):raise ValueError('Authentication destination excluded')
  tree=html.fromstring(raw)
  for node in tree.xpath('//script|//style|//nav|//header|//footer|//noscript'):node.drop_tree()
  main=tree.xpath('//main|//*[@role="main"]')
  text=' '.join((main[0] if main else tree).text_content().split())
  if len(text)<100 or re.search(r'access denied|request rejected|sign in to your account',text,re.I):raise ValueError('No usable public content')
  title=' '.join(tree.xpath('//title/text()')).strip()
  if title:row['title']=title
  if row['source_type']=='programme_information':
   article=tree.xpath('//article[contains(@class,"prog-detail")]')
   body=' '.join((article[0] if article else (main[0] if main else tree)).text_content().split())
   entry=re.search(r'\b(Sept(?:ember)?|Jan(?:uary)?)\s+(20\d{2})\s+Entry\b',body,re.I)
   entry_basis='explicit_visible_entry_term_mapped_to_academic_year'
   if not entry:
    entry=re.search(r'\b(Sept(?:ember)?|Jan(?:uary)?)\s+(20\d{2})\s+Entry\b',catalogue_label,re.I)
    if not entry or urlparse(final).path!=urlparse(row['requested_url']).path:raise ValueError('Visible programme/catalogue entry label missing or detail redirected')
    entry_basis='explicit_official_catalogue_card_entry_label_detail_not_english_dated'
   term='January' if entry[1].lower().startswith('jan') else 'September';year=int(entry[2])
   first=year-1 if term=='January' else year
   last=urlparse(final).path.rstrip('/').split('/')[-1]
   code=last.upper() if last.lower().startswith('js') else (re.match(r'\d{5}',last).group(0) if re.match(r'\d{5}',last) else '')
   if not code:raise ValueError('Programme identifier unavailable')
   row.update(programme_code=code,entry_year=year,entry_term=term,academic_year=f'{first}/{str(first+1)[-2:]}',year_basis=entry_basis,catalogue_label=catalogue_label)
   faculties=['Faculty of Business','Faculty of Computer and Mathematical Sciences','Faculty of Construction and Environment','Faculty of Engineering','Faculty of Health and Social Sciences','Faculty of Humanities','Faculty of Science','School of Design','School of Fashion and Textiles','School of Hotel and Tourism Management','College of Undergraduate Studies','Graduate School']
   found=[f for f in faculties if f in body]
   if len(found)==1:row.update(faculty=found[0],unit=found[0])
  slug=hashlib.sha256(final.encode()).hexdigest()[:18]
  group={'programme_information':'programmes','programme_directory':'catalogues','research_programme_information':'research_programmes','student_service':'student_services'}[row['source_type']]
  path=OUT/group/(slug+'.html');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
  row.update(status='downloaded',source_url=final,file_path=path.relative_to(ROOT).as_posix(),file_type='html',
             captured_at=stamp(),sha256=hashlib.sha256(raw).hexdigest(),
             notes='Public programme/service snapshot. Admissions information is not a cohort PRD, live vacancy or proof of personal eligibility. Preserve admission pathway, entry term and all conditions. Undated pages have no inferred academic year.')
 except Exception as e:row['error']=str(e)
 time.sleep(.25)
 return row

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 targets,discovery=make_tasks()
 if len(targets)>1200:raise ValueError('Unexpected collection size; review links')
 with (ROOT/'data/sources.csv').open(encoding='utf-8-sig',newline='') as f:existing={canonical(r['source_url']):r for r in csv.DictReader(f) if not r['file_path'].startswith('files/schoolwide/')}
 path=OUT/'download_manifest.json'
 previous={canonical(r['requested_url']):r for r in json.loads(path.read_text(encoding='utf-8'))} if path.exists() else {}
 rows=[];pending=[]
 for row in targets:
  key=canonical(row['requested_url'])
  if key in existing:
   rows.append(dict(row,status='already_indexed',existing_source_id=existing[key]['source_id'],file_path=existing[key]['file_path']))
  elif key in previous and previous[key]['status']=='downloaded':
   cached=dict(previous[key])
   for field in ['faculty','unit','student_type','page_type']:
    if row.get(field):cached[field]=row[field]
   rows.append(cached)
  elif key in previous and previous[key]['status'] in {'failed','duplicate_redirect'} and row['source_type']!='programme_information':rows.append(previous[key])
  else:pending.append(row)
 print(f'Discovered {len(targets)} URLs; {len(pending)} new requests; {len(rows)} indexed/cached.',flush=True)
 with ThreadPoolExecutor(max_workers=4) as pool:
  for i,row in enumerate(pool.map(download,pending),1):
   rows.append(row)
   path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
   if i%25==0 or row['status']=='failed':print(i,len(pending),row['status'],row['requested_url'],row.get('error',''),flush=True)
 seen={}
 for row in rows:
  if row['status']!='downloaded':continue
  key=canonical(row['source_url'])
  if key in existing:
   row.update(status='already_indexed',existing_source_id=existing[key]['source_id'])
  elif key in seen:
   row.update(status='duplicate_redirect',canonical_file_path=seen[key])
  else:seen[key]=row['file_path']
 path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 print('DONE',len(rows),'rows;',sum(r['status']=='downloaded' for r in rows),'new validated sources',flush=True)

if __name__=='__main__':main()
