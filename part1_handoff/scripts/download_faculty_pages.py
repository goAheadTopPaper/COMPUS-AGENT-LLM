"""Download a bounded set of public official academic-unit pages.

Uses the user's saved PolyU academic directory as the seed. Up to four HTML
pages per unit: home, overview, programme listing and contact/student information.
No login, library database, deep crawl, staff biographies or news archive crawl.
"""
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'files/faculty wise rules'
DIRECTORY_URL = 'https://www.polyu.edu.hk/en/education/faculties-schools-departments/'
LABELS = {
    'Faculty of Business':'Business',
    'Faculty of Computer and Mathematical Sciences':'FCMS',
    'Faculty of Construction and Environment':'Construction_Environment',
    'Faculty of Engineering':'Engineering',
    'Faculty of Health and Social Sciences':'Health_Social_Sciences',
    'Faculty of Humanities':'Humanities',
    'Faculty of Science':'Science',
    'School of Design':'Design',
    'School of Fashion and Textiles':'Fashion_Textiles',
    'School of Hotel and Tourism Management':'Hotel_Tourism',
}
CACHE = {}


def official(url):
    host = (urlparse(url).hostname or '').lower()
    return urlparse(url).scheme in {'http','https'} and (host == 'polyu.edu.hk' or host.endswith('.polyu.edu.hk'))


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not official(newurl):
            raise ValueError('Redirect left the official PolyU domain')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def fetch(url):
    if not official(url):
        raise ValueError('Non-official URL rejected')
    if url in CACHE:
        saved = CACHE[url]
        data = (ROOT / saved['file_path']).read_bytes()
        if hashlib.sha256(data).hexdigest() == saved['sha256']:
            return data, html.fromstring(data,base_url=saved['source_url']), saved['source_url'], saved['title']
    request = Request(url,headers={'User-Agent':'PolyU-COMP5584-StudentProject/1.0 (bounded academic information collection)', 'Accept':'text/html'})
    with build_opener(OfficialRedirect).open(request,timeout=25) as response:
        if 'html' not in response.headers.get('Content-Type','').lower():
            raise ValueError('Not an HTML page')
        data = response.read(6_000_001)
        if len(data) > 6_000_000:
            raise ValueError('HTML size limit exceeded')
        final = response.geturl()
    tree = html.fromstring(data,base_url=final)
    title = ' '.join(tree.xpath('//title/text()')).strip()
    if re.search(r'access denied|request rejected|just a moment|403 forbidden',title,re.I):
        raise ValueError(f'Access/challenge page: {title}')
    return data, tree, final, title


def get_units():
    candidates = [p for p in OUT.glob('*.html') if 'Faculties' in p.name]
    if not candidates:
        raise ValueError('Save the official faculty directory in files/faculty wise rules first')
    tree = html.fromstring(candidates[0].read_bytes())
    units = []
    seen = set()
    faculty = ''
    for anchor in tree.xpath('//a[@href]'):
        label = ' '.join(anchor.text_content().split())
        if not label.startswith(('Faculty of ','Department of ','School of ','Division of ')):
            continue
        url = urljoin(DIRECTORY_URL,anchor.get('href'))
        if label in seen or not official(url):
            continue
        seen.add(label)
        if label.startswith('Faculty of '):
            faculty = label
        parent = faculty if label not in LABELS else label
        slug = LABELS.get(label) or re.sub(r'[^A-Za-z0-9]+','_',label).strip('_')
        # Directory links sometimes use HTTP; request HTTPS for the same host/path.
        url = 'https://' + url.split('://',1)[1]
        units.append(dict(unit=label,faculty=parent,slug=slug,url=url))
    return units


def same_unit(url,home):
    a,b = urlparse(url),urlparse(home)
    if a.hostname != b.hostname:
        return False
    def parts(path):
        return [x for x in path.lower().split('/') if x and x not in {'en','tc','sc','eng','english'}]
    first = parts(b.path)
    return not first or parts(a.path)[:1] == first[:1]


def choose_links(tree,home):
    pools = {'Overview':[], 'Programmes':[], 'Contact':[]}
    for anchor in tree.xpath('//a[@href]'):
        label = ' '.join(anchor.text_content().split())
        url = urljoin(home,anchor.get('href'))
        parsed = urlparse(url)
        url = urlunparse(parsed._replace(fragment=''))
        text = label.lower()
        if not official(url) or not same_unit(url,home) or url.rstrip('/') == home.rstrip('/'):
            continue
        if re.search(r'\.(pdf|jpg|png|docx?|xlsx?|zip)(?:\?|$)',url,re.I):
            continue
        if any(x in url.lower() for x in ['/tc/','/sc/','/news/','/events/','/staff/','/people/','/research/','/search-result/']):
            continue
        for kind,words in {
            'Overview':['overview','introduction','about us','about the faculty','about the school','about the department','about','message from','dean\'s message','head\'s message'],
            'Programmes':['taught postgraduate','postgraduate programmes','academic programmes','programmes','programs','study'],
            'Contact':['contact us','contact','student enquiries','student support'],
        }.items():
            for rank,word in enumerate(words):
                if word in text:
                    score = 100-rank*5 - len(text)/20
                    if kind == 'Overview' and ('dean' in text or 'head' in text):
                        score -= 40
                    pools[kind].append((score,url,label))
                    break
    chosen = []
    used = set()
    for kind,items in pools.items():
        for _,url,label in sorted(items,reverse=True):
            if url not in used:
                used.add(url)
                chosen.append((kind,url,label))
                break
    return chosen


def save_page(unit,kind,url,result):
    data,tree,final,title = result
    folder = OUT / ('faculties_and_schools' if unit['unit'] in LABELS else 'departments') / unit['slug']
    folder.mkdir(parents=True,exist_ok=True)
    filename = f'{unit["slug"]}_{kind}.html'
    path = folder / filename
    # HTML is an original server snapshot, not a browser-rendered/offline-complete website.
    path.write_bytes(data)
    for node in tree.xpath('//script|//style|//noscript|//svg|//nav|//header|//footer'):
        node.drop_tree()
    for node in tree.xpath('//p|//li|//h1|//h2|//h3|//h4|//tr|//br'):
        node.tail = '\n' + (node.tail or '')
    main = tree.xpath('//main|//*[@role="main"]')
    text = (main[0] if main else tree).text_content()
    text = '\n'.join(re.sub(r'\s+',' ',line).strip() for line in text.splitlines() if line.strip())
    path.with_suffix('.txt').write_text(text,encoding='utf-8')
    return dict(unit=unit['unit'],faculty=unit['faculty'],page_type=kind,title=title,
                requested_url=url,source_url=final,file_path=path.relative_to(ROOT).as_posix(),
                captured_at=CACHE.get(url,{}).get('captured_at') or datetime.now(timezone(timedelta(hours=8))).isoformat(),
                academic_year='not_specified',source_type='academic_unit_information',
                status='downloaded' if len(text)>200 else 'downloaded_needs_rendering_review',
                text_characters=len(text),sha256=hashlib.sha256(data).hexdigest(),
                notes='Public HTML snapshot; no login; not an academic regulation or proof of programme eligibility. Current-page information is not necessarily cohort-2026 rules.')


def download_unit(unit):
    rows = []
    try:
        result = fetch(unit['url'])
        links = choose_links(result[1],result[2])
        rows.append(save_page(unit,'Home',unit['url'],result))
        for kind,url,label in links:
            time.sleep(0.4)
            try:
                rows.append(save_page(unit,kind,url,fetch(url)))
            except Exception as exc:
                rows.append(dict(unit=unit['unit'],faculty=unit['faculty'],page_type=kind,requested_url=url,status='failed',notes=str(exc)))
    except Exception as exc:
        rows.append(dict(unit=unit['unit'],faculty=unit['faculty'],page_type='Home',requested_url=unit['url'],status='failed',notes=str(exc)))
    print(f'{unit["unit"]}: {sum(r["status"].startswith("downloaded") for r in rows)} pages saved',flush=True)
    return rows


def main():
    manifest = OUT / 'download_manifest.json'
    if manifest.exists():
        CACHE.update({r['requested_url']:r for r in json.loads(manifest.read_text(encoding='utf-8'))
                      if r['status'].startswith('downloaded') and (ROOT / r['file_path']).is_file()})
    units = get_units()
    print(f'Collecting up to four public HTML pages for each of {len(units)} academic units.',flush=True)
    rows = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(download_unit,units):
            rows.extend(result)
            (OUT / 'download_manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    fields = ['unit','faculty','page_type','title','requested_url','source_url','file_path','captured_at','academic_year','source_type','status','text_characters','sha256','notes']
    with (OUT / 'download_manifest.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    failed = [r for r in rows if r['status']=='failed']
    downloaded = [r for r in rows if r['status'].startswith('downloaded')]
    report = (
        '# Faculty and department collection\n\n'
        f'Academic units attempted: {len(units)}. HTML pages saved: {len(downloaded)}. Failed page requests: {len(failed)}.\n\n'
        'Sources were discovered from the saved official PolyU academic-unit directory. Each unit has at most four pages: homepage and available overview/programme/contact links. This is not a full website mirror or complete coverage of all programme requirements.\n\n'
        'HTML files are raw server snapshots; CSS, images and scripts were not mirrored. Plain-text companions provide an extraction preview. Dynamic pages and text quality need review. No login or library database was accessed.\n\n'
        'These files are staged and are not yet included in the policy retrieval index. They must be classified as academic-unit information separately from rules. See download_manifest.csv for URLs, capture times, hashes and failures.\n\n'
        '## Failed requests\n\n' + '\n'.join(f'- {r["unit"]} / {r["page_type"]}: {r["requested_url"]} — {r["notes"]}' for r in failed)
    )
    (OUT / 'COLLECTION_README.md').write_text(report,encoding='utf-8')
    print(f'DONE: {len(downloaded)} saved; {len(failed)} failed. Manifest and review notes saved.',flush=True)


if __name__ == '__main__':
    main()
