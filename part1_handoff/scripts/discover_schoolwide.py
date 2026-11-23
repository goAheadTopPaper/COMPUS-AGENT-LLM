"""Fetch official catalogue/service entry points and enumerate public links."""
import json
from pathlib import Path
from urllib.parse import urljoin,urlparse
from lxml import html
from download_year_sources import request,stamp
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'files/schoolwide'
SEEDS={
 'ug':'https://www.polyu.edu.hk/study/ug/programmes/find-your-programmes',
 'tpg':'https://www.polyu.edu.hk/study/pg/taught-postgraduate/find-your-programmes-tpg',
 'rpg':'https://www.polyu.edu.hk/gs/prospective-students/how-to-apply/find-a-programme/?sc_lang=en',
 'services':'https://www.polyu.edu.hk/sao/',
 'research_admissions':'https://www.polyu.edu.hk/study/pg/research-postgraduate/research-postgraduate-application-period',
 'ug_non_jupas':'https://www.polyu.edu.hk/study/ug/programmes/find-your-programmes?ug_programmes_label_target_id_verf=prog_detail_nj',
 'ug_senior_year':'https://www.polyu.edu.hk/study/ug/programmes/find-your-programmes?ug_programmes_label_target_id_verf=prog_detail_njh',
 'ug_international':'https://www.polyu.edu.hk/study/ug/programmes/find-your-programmes?ug_programmes_label_target_id_verf=prog_detail_international',
 'ug_mainland':'https://www.polyu.edu.hk/study/ug/programmes/find-your-programmes?ug_programmes_label_target_id_verf=prog_detail_jee',
 'tpg_january':'https://www.polyu.edu.hk/study/pg/taught-postgraduate/find-your-programmes-tpg?pg_programmes_semester_term_value=2666',
 'it_services':'https://www.polyu.edu.hk/its/students/it-services-for-students/?sc_lang=en',
 'health_services':'https://www.polyu.edu.hk/uhs/?sc_lang=en',
 'library_services':'https://www.lib.polyu.edu.hk/services',
}
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 previous=OUT/'discovery.json'
 cached={r['source_url']:r for r in json.loads(previous.read_text(encoding='utf-8')) if r['status']=='downloaded'} if previous.exists() else {}
 rows=[]
 queue=list(SEEDS.items())
 visited=set()
 for name,url in queue:
  if url in visited:continue
  visited.add(url)
  try:
   if url in cached:
    record=cached[url]; path=ROOT/record['file_path']; raw=path.read_bytes();final=url
   else:
    raw,final,_=request(url)
    path=OUT/'indexes'/(name+'.html'); path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
   tree=html.fromstring(raw)
   links=[]
   for a in tree.xpath('//a[@href]'):
    target=urljoin(final,a.get('href','')).split('#')[0]
    host=urlparse(target).hostname or ''
    if host!='polyu.edu.hk' and not host.endswith('.polyu.edu.hk'):continue
    label=' '.join(a.text_content().split())
    if label:links.append(dict(url=target,label=label))
   rows.append(dict(name=name,source_url=final,file_path=path.relative_to(ROOT).as_posix(),captured_at=cached[url]['captured_at'] if url in cached else stamp(),status='downloaded',links=links))
   if name.startswith('ug'):
    for a in tree.xpath('//ul[contains(@class,"pager")]//a[@href]'):
     target=urljoin(final,a.get('href'))
     if target not in visited:
      if len(queue)>100:raise ValueError('Unexpected pagination size; review catalogue')
      queue.append((name.split('_page')[0]+'_page'+str(len(queue)),target))
   print(name,len(links),flush=True)
  except Exception as e:
   rows.append(dict(name=name,source_url=url,status='failed',error=str(e)))
 (OUT/'discovery.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
