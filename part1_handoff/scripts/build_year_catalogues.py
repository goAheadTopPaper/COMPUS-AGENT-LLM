"""Create clearly labelled local faculty lists from verified dated programme pages."""
from collections import defaultdict
from html import escape
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'files/year_specific'
URL='https://www.polyu.edu.hk/study/pg/taught-postgraduate/find-your-programmes-tpg'


def main():
    from lxml import html
    manifest=BASE/'download_manifest.json'
    rows=[r for r in json.loads(manifest.read_text(encoding='utf-8')) if r['source_type']!='programme_catalogue']
    tree=html.fromstring((BASE/'TPg_Catalogue.html').read_bytes())
    labels={urljoin(URL,a.get('href','')).split('?')[0]:' '.join(a.text_content().split()) for a in tree.xpath('//a[@href]')}
    groups=defaultdict(list)
    for row in rows:
        if row['status']=='downloaded' and row['source_type']=='programme_information':
            row['catalogue_label']=labels.get(row['source_url'],'')
            groups[(row['faculty'],row['academic_year'],row['entry_year'],row['entry_term'])].append(row)
    for (faculty,year,entry,term),items in sorted(groups.items()):
        title=f'{faculty}: Taught Postgraduate Programmes for {term} {entry} Entry ({year})'
        parts=[f'<html><head><meta charset="utf-8"><title>{escape(title)}</title></head><body><main><h1>{escape(title)}</h1>',
               '<p>Locally assembled catalogue of verified downloaded official programme pages. This is a dated subset, not a guarantee of all university offerings or admission availability.</p>']
        for item in sorted(items,key=lambda r:r['programme_code']):
            name=item['title'].split(' - ',1)[-1].split(' | ',1)[0]
            parts.append(f'<p>{escape(name)}<br>Programme Code: {item["programme_code"]}<br>Entry: {term} {entry}<br>Source: <a href="{escape(item["source_url"],quote=True)}">{escape(item["source_url"])}</a></p>')
            if 'subject to approval' in item.get('catalogue_label','').lower():
                parts.append('<p>Availability condition: This programme is offered subject to approval.</p>')
        parts.append('</main></body></html>')
        data='\n'.join(parts).encode('utf-8')
        slug=re.sub(r'[^A-Za-z0-9]+','_',faculty).strip('_')
        path=BASE/'catalogues'/year.replace('/','-')/(slug+'.html')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
        rows.append(dict(status='downloaded',requested_url=URL,source_url=URL,file_path=path.relative_to(ROOT).as_posix(),
                         title=title,source_type='programme_catalogue',faculty=faculty,academic_year=year,entry_year=entry,entry_term=term,
                         year_basis='derived_from_verified_entry_labelled_programme_pages',captured_at=max(r['captured_at'] for r in items),
                         sha256=hashlib.sha256(data).hexdigest(),programme_count=len(items),
                         notes='Locally derived faculty catalogue from verified downloaded entry-year pages. Original per-programme source URLs are included. Not an official cohort PRD or a complete historical programme census.'))
    manifest.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Created {len(groups)} year-labelled faculty catalogues from verified programme pages.')


if __name__=='__main__':
    main()
