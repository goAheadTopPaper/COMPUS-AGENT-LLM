"""Collect public year-labelled TPg programme pages and annual handbooks.

Discover programme URLs from the official catalogue; try their 2026/2027 entry
versions, accepting only pages whose visible ENTRY agrees with the requested year.
HTTP errors/redirects without matching entry labels are logged, not relabelled.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin,urlparse
from urllib.request import Request,build_opener
from lxml import html
from pypdf import PdfReader
from download_faculty_pages import OfficialRedirect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'files/year_specific'
CATALOGUE='https://www.polyu.edu.hk/study/pg/taught-postgraduate/find-your-programmes-tpg'


def request(url):
    req=Request(url,headers={'User-Agent':'PolyU-COMP5584-StudentProject/1.0 (year-specific academic information collection)'})
    with build_opener(OfficialRedirect).open(req,timeout=20) as response:
        data=response.read(25_000_001)
        if len(data)>25_000_000:
            raise ValueError('Document exceeds collection size limit')
        return data,response.geturl(),response.headers.get('Content-Type','')


def stamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def programme(task):
    url,faculty,year=task
    row=dict(requested_url=url,source_type='programme_information',faculty=faculty,status='failed',requested_entry_year=year)
    try:
        data,final,ctype=request(url)
        if 'html' not in ctype:
            raise ValueError('Expected HTML')
        tree=html.fromstring(data)
        title=' '.join(tree.xpath('//title/text()')).strip()
        text=' '.join(tree.text_content().split())
        # There can be ENTRY labels in navigation or dates elsewhere. Require the
        # specific Entry label; application-deadline years are not source versions.
        entries=re.findall(r'\b(Sept(?:ember)?|Jan(?:uary)?)\s+(20\d{2})\s+Entry\b',text,re.I)
        entries=list(dict.fromkeys((m.lower(),int(y)) for m,y in entries))
        matching=[(m,y) for m,y in entries if y==year]
        code=re.search(r'/tpg/20\d{2}/(\d{5})',final)
        if not code or not matching:
            raise ValueError(f'No matching visible entry year; entry labels found: {entries}')
        month,_=matching[0]
        academic_start=year if month.startswith('sept') else year-1
        academic_year=f'{academic_start}/{str(academic_start+1)[2:]}'
        path=OUT/'programmes'/str(year)/(urlparse(url).path.rstrip('/').split('/')[-1]+'.html')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
        row.update(status='downloaded',source_url=final,file_path=path.relative_to(ROOT).as_posix(),title=title,
                   programme_code=code.group(1),entry_year=year,entry_term='September' if month.startswith('sept') else 'January',
                   academic_year=academic_year,year_basis='entry_term_mapped_to_academic_year',
                   captured_at=stamp(),sha256=hashlib.sha256(data).hexdigest(),
                   notes='Year-specific admissions/programme information. Not a cohort-specific PRD or proof of subject availability; preserve conditions and subject-to-approval labels.')
    except Exception as exc:
        row['notes']=str(exc)
    time.sleep(0.25)
    return row


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=[]
    # Existing cached snapshots avoid repeated requests on later rebuilds.
    manifest_path=OUT/'download_manifest.json'
    previous=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else []
    cached={r['requested_url']:r for r in previous if r['status']=='downloaded' and (ROOT/r['file_path']).is_file()}
    previous_by_url={r['requested_url']:r for r in previous}
    if (OUT/'TPg_Catalogue.html').exists():
        data=(OUT/'TPg_Catalogue.html').read_bytes()
        final=CATALOGUE
    else:
        data,final,_=request(CATALOGUE)
        (OUT/'TPg_Catalogue.html').write_bytes(data)
    tree=html.fromstring(data)
    tasks=[]
    seen=set()
    faculty=''
    # Read headings/links in source order to retain faculty grouping.
    for node in tree.iter():
        label=' '.join(node.text_content().split()) if node.tag in {'a','h2','h3','h4'} or node.get('class')=='faculty-title' else ''
        if node.get('class')=='faculty-title':
            faculty=label
        if node.tag!='a':
            continue
        url=urljoin(final,node.get('href',''))
        if not re.search(r'/study/pg/tpg/2027/\d{5}',url):
            continue
        for year in [2026,2027]:
            target=url.replace('/tpg/2027/',f'/tpg/{year}/').split('?')[0].split('#')[0]
            if target not in seen:
                tasks.append((target,faculty,year))
                seen.add(target)
    if not tasks:
        raise ValueError('No programme links found; catalogue layout requires review')
    if len(tasks)>360:
        raise ValueError('Collection limit exceeded; review the discovered URLs before expanding')
    print(f'Programme pages to check: {len(tasks)} (2026 and 2027 entry versions).',flush=True)
    pending=[]
    for task in tasks:
        if task[0] in previous_by_url:
            row=dict(previous_by_url[task[0]],faculty=task[1])
            rows.append(row)
        else:
            pending.append(task)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index,row in enumerate(pool.map(programme,pending),1):
            rows.append(row)
            manifest_path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
            if index%20==0:
                print(f'Checked {index}/{len(pending)}; saved {sum(r["status"]=="downloaded" for r in rows)} programme pages.',flush=True)
    for year in ['2024-25','2025-26']:
        url=f'https://www.polyu.edu.hk/ar/docdrive/polyu-students/student-handbook/Student_Handbook_{year}_English.pdf'
        if url in cached:
            rows.append(cached[url])
            continue
        row=dict(requested_url=url,source_type='handbook',status='failed')
        try:
            raw,final,_=request(url)
            reader=PdfReader(io.BytesIO(raw))
            front=' '.join(p.extract_text() or '' for p in reader.pages[:4])
            academic_year=year[:4]+'/'+year[-2:]
            if academic_year not in front:
                raise ValueError('Handbook front pages do not confirm requested academic year')
            path=OUT/'handbooks'/f'Student_Handbook_{year}_English.pdf'
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(raw)
            row.update(status='downloaded',source_url=final,file_path=path.relative_to(ROOT).as_posix(),
                       title=f'Student Handbook for Taught Programmes {academic_year}',academic_year=academic_year,
                       year_basis='explicit_handbook_academic_year',captured_at=stamp(),sha256=hashlib.sha256(raw).hexdigest(),
                       notes='Annual handbook; retain internal cohort exceptions. Historical source, not necessarily current policy.')
        except Exception as exc:
            row['notes']=str(exc)
        rows.append(row)
    manifest_path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    success=[r for r in rows if r['status']=='downloaded']
    print(f'DONE: {len(success)} verified year-labelled sources; {len(rows)-len(success)} unavailable or unverified URLs logged.',flush=True)


if __name__=='__main__':
    main()
