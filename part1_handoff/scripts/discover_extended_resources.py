"""Save public resource indexes and enumerate their document links for review."""
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse
from lxml import html
from download_year_sources import request, stamp

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'files/extended_resources'
SEEDS={
 'comp_mt_subjects':'https://www.polyu.edu.hk/comp/study/taught-postgraduate-programme/mscmt/subjects/',
 'comp_mt_curriculum':'https://www.polyu.edu.hk/comp/study/taught-postgraduate-programme/mscmt/curriculum/',
 'comp_mt_faq':'https://www.polyu.edu.hk/comp/study/taught-postgraduate-programme/mscmt/faq/',
 'eee_prds':'https://www.polyu.edu.hk/eee/study/information-for-current-students/programme-documents/',
 'aae_prds':'https://www.polyu.edu.hk/aae/study/programme-requirement-documents/',
 'me_students':'https://www.polyu.edu.hk/me/study/course-info/',
 'dsai_aibd_curriculum':'https://www.polyu.edu.hk/dsai/study/tpg/mscaibd/curriculum/',
 'fb_bm_resources':'https://www.polyu.edu.hk/fb/study/tpg-landing/tpg/bm/resources/',
 'science_prds':'https://www.polyu.edu.hk/fs/study/undergraduate-programme/current-students/bachelors-degree-scheme-in-science/programme-requirement-document/',
}

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 rows=[]
 for name,url in SEEDS.items():
  path=OUT/'indexes'/f'{name}.html'
  try:
   if path.exists():
    raw=path.read_bytes(); final=url
   else:
    raw,final,_=request(url); path.parent.mkdir(exist_ok=True); path.write_bytes(raw)
   tree=html.fromstring(raw)
   links=[]
   for a in tree.xpath('//a[@href]'):
    target=urljoin(final,a.get('href'))
    host=urlparse(target).hostname or ''
    if not (host=='polyu.edu.hk' or host.endswith('.polyu.edu.hk')): continue
    label=' '.join(a.text_content().split())
    if '.pdf' in target.lower() or 'handbook' in label.lower() or 'requirement document' in label.lower() or ('2026' in label and 'fbweb.polyu.edu.hk' in target):
     parent=a.getparent()
     table=a.xpath('ancestor::tr[1]')
     context=' '.join((table[0] if table else parent).text_content().split())[:700]
     headings=a.xpath('preceding::*[self::h2 or self::h3 or self::h4][1]')
     links.append(dict(url=target,label=label,context=context,heading=' '.join(headings[0].text_content().split()) if headings else ''))
   rows.append(dict(name=name,source_url=final,file_path=path.relative_to(ROOT).as_posix(),captured_at=stamp(),links=links,status='downloaded'))
   print(name,len(links),flush=True)
  except Exception as e:
   rows.append(dict(name=name,source_url=url,status='failed',error=str(e)))
   print(name,str(e),flush=True)
 (OUT/'discovery.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
