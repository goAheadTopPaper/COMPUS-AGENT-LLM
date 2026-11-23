"""Write the complete structured programme directory and coverage inventory."""
from collections import Counter
import csv
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]

def main():
 with (ROOT/'data/sources.csv').open(encoding='utf-8-sig',newline='') as f:sources=list(csv.DictReader(f))
 keys=['source_id','title','source_url','programme','student_type','academic_year','entry_year','entry_term','admission_pathway','faculty','captured_at']
 directory=[{key:x.get(key,'') for key in keys} for x in sources if x['source_type']=='programme_information']
 for row in directory:row['programme_code']=row.pop('programme')
 directory.sort(key=lambda x:(x['student_type'],x['programme_code'],x['entry_term'],x['admission_pathway'],x['source_url']))
 (ROOT/'data/programme_directory.json').write_text(json.dumps(directory,ensure_ascii=False,indent=2),encoding='utf-8')
 rows=json.loads((ROOT/'files/schoolwide/download_manifest.json').read_text(encoding='utf-8'))
 total=len(sources); extraction=json.loads((ROOT/'data/extraction_report.json').read_text(encoding='utf-8'))
 # Reports always describe the actual generated collection, not a fixed target.
 report=dict(source_count=total,passage_count=extraction['chunks'],programme_detail_records=len(directory),
             undergraduate_pathway_counts=dict(Counter(x['admission_pathway'] for x in directory if x['student_type']=='undergraduate')),
             postgraduate_entry_counts=dict(Counter(x['entry_term']+' '+x['entry_year'] for x in directory if x['student_type']=='taught_postgraduate')),
             research_link_counts=dict(Counter(x['status'] for x in rows if x['source_type']=='research_programme_information')),
             service_sources=sum(x['source_type']=='student_service' for x in sources),
             unresolved=[dict(url=x['requested_url'],kind=x['source_type'],reason=x.get('error','')) for x in rows if x['status']=='failed'])
 (ROOT/'data/schoolwide_coverage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# School-wide public catalogue and service coverage','',
        'Captured from official PolyU public links on 20 November 2026 (Hong Kong time).',
        f'Active corpus: {total} sources and {extraction["chunks"]} cited passages.', '',
        f'Programme detail-page records: {len(directory)}. These are pages/pathways/specialisms, not a count of unique degrees.', '',
        '## Catalogue scope','',
        'All detail links discovered in the saved central undergraduate and taught-postgraduate catalogues are included. All undergraduate Show More links were followed through the final page.',
        'Undergraduate pathway counts: '+str(report['undergraduate_pathway_counts']),
        'Taught postgraduate entries: '+str(report['postgraduate_entry_counts']),
        'The full Graduate School research-programme directory is included. Research link outcomes: '+str(report['research_link_counts']),
        'Research units without accessible detail pages remain identifiable in the official directory; a directory entry is not a full programme document.', '',
        '## Service scope','',
        f'{report["service_sources"]} service sources in the active corpus: financial assistance, scholarships, halls/housing, non-local students, visa guidance, special needs, careers, sports, counselling, IT, health, orientation and Library guidance.',
        'Some service navigation pages are empty or unavailable; failures are listed below. Private/account-specific services are excluded.', '',
        '## Use the appropriate tool','',
        'Use policy_rag.directory.list_programmes() for a complete catalogue listing; passage retrieval returns only top-k evidence and must not be presented as an exhaustive university list.',
        'Use PolicyRetriever.search() for questions about particular programmes, rules or services. Specify entry_term and admission_pathway where applicable.',
        'January 2027 entry maps to academic year 2026/27; September 2027 maps to 2027/28. These do not establish September 2026 cohort requirements.',
        'The default catalogue reflects the public admissions cycle. It is not a full historical census or full PRDs for every programme/cohort.',
        'The 13 validated 2026/27 PRDs remain partial coverage. A listing or admissions page must not be described as a PRD.',
        'Chinese-language admissions pages are preserved, but the English MiniLM model has not been validated for Chinese question answering.',
        'Existing FAQ currency and PDF/OCR limitations remain; see the extended_resources collection notes.', '',
        '## Unresolved links','']
 lines += [f'- {x["kind"]}: {x["url"]} — {x["reason"]}' for x in report['unresolved']]
 lines += ['', '## Example commands','', '```powershell',
           'python -X utf8 -m policy_rag.directory --student-type undergraduate --admission-pathway jupas --output data/all_jupas_programmes.json',
           'python -X utf8 -m policy_rag.directory --student-type taught_postgraduate --entry-term January --output data/all_january_programmes.json',
           'python -X utf8 -m policy_rag.retrieve --query "What is the curriculum of JS3060?" --programme-code JS3060 --admission-pathway jupas --entry-year 2027 --entry-term September --method hybrid --offline',
           'python -X utf8 -m policy_rag.retrieve --query "What is the PolyU Emergency Financial Assistance Scheme?" --domain student_services --method hybrid --offline',
           '```','']
 (ROOT/'files/schoolwide/COLLECTION_README.md').write_text('\n'.join(lines),encoding='utf-8')
 for filename in ['README.md','PART1_GUIDE.md','START_HERE.md']:
  path=ROOT/filename;text=path.read_text(encoding='utf-8')
  text=text.replace('421 sources and 7,403 cited passages',f'{total} sources and {extraction["chunks"]:,} cited passages')
  text=text.replace('421 sources and 7,403',f'{total} sources and {extraction["chunks"]:,}')
  text=text.replace('421 indexed sources',f'{total} indexed sources').replace('7,403 cited passages',f'{extraction["chunks"]:,} cited passages')
  text=text.replace('421 catalogued sources',f'{total} catalogued sources').replace('7,403 passages',f'{extraction["chunks"]:,} passages')
  path.write_text(text,encoding='utf-8')
 print('Saved complete programme directory and school-wide coverage:',total,'sources;',extraction['chunks'],'passages.')

if __name__=='__main__':main()
