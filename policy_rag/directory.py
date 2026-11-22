"""Complete catalogue listing without the top-k limit of passage retrieval."""
import argparse
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def list_programmes(student_type=None,entry_year=None,entry_term=None,admission_pathway=None):
    rows=json.loads((ROOT/'data/programme_directory.json').read_text(encoding='utf-8'))
    filters=dict(student_type=student_type,entry_year=str(entry_year) if entry_year is not None else None,
                 entry_term=entry_term,admission_pathway=admission_pathway)
    selected=[row for row in rows if all(value is None or str(row.get(key,''))==value for key,value in filters.items())]
    return dict(status='catalogue_listing',count=len(selected),filters=filters,programmes=selected,
                limitations=['All matching detail-page records in the saved official catalogues, not all historical programmes or PRDs.',
                             'Admission pathways, specialisms and entry terms can share a programme code. Do not count pages as unique degrees.'])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--student-type',choices=['undergraduate','taught_postgraduate'])
    p.add_argument('--entry-year',type=int)
    p.add_argument('--entry-term',choices=['January','September'])
    p.add_argument('--admission-pathway')
    p.add_argument('--output',required=True)
    a=p.parse_args()
    result=list_programmes(a.student_type,a.entry_year,a.entry_term,a.admission_pathway)
    path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Saved {result["count"]} programme records to {path}')
if __name__=='__main__':main()
