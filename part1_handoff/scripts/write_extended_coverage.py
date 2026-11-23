"""Write a compact inventory and explicit currency/coverage limits."""
from collections import Counter
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
 folder=ROOT/'files/extended_resources'
 rows=json.loads((folder/'download_manifest.json').read_text(encoding='utf-8'))
 selected=[r for r in rows if r['status']=='downloaded']
 audit=json.loads((ROOT/'data/source_currency_checks.json').read_text(encoding='utf-8')) if (ROOT/'data/source_currency_checks.json').exists() else {'results':[]}
 counts=dict(Counter(r['source_type'] for r in selected))
 report=dict(added_sources=len(selected),source_counts=counts,
             prd_programme_codes=sorted(r['programme_code'] for r in selected if r['source_type']=='programme_requirements'),
             unresolved=[r for r in rows if r['status'] not in {'downloaded','archived_outdated'}],
             excluded_historical=[r for r in rows if r['status']=='archived_outdated'],
             currency_counts=dict(Counter(r['status'] for r in audit['results'])),
             verified_date='2026-11-19',coverage='Partial public-source collection, not all programmes/cohorts or all PolyU questions.')
 (ROOT/'data/extended_coverage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# Extended public-source collection','',
        'Official public links downloaded and checked on 19 November 2026 (Hong Kong time).',
        'This is a dated snapshot; it does not update itself.','',
        f'Added active sources: {len(selected)}. Counts: {counts}.','',
        '## Included 2026/27 programme requirement documents','',
        '| Programme code | Unit | PDF pages |','|---|---|---|']
 for row in selected:
  if row['source_type']=='programme_requirements':
   lines.append(f"| {row['programme_code']} | {row['unit']} | {row['pages']} |")
 lines += ['', 'Programme codes identify the downloaded scheme/programme document. They do not imply that every specialism or entry pathway is covered.',
           'The document year and programme code were checked in extracted PDF text and against the official linked version.',
           'Cohort applicability must still be checked inside the PRD. No admission cohort or calendar entry year was invented.', '',
           '## Subject descriptions and services','',
           '75 public Computing subject PDFs were discovered from the official subject list. Subject codes were checked against PDF contents.',
           'These are the versions served by those official links at capture time; some show older revision dates. They are not proof of 2026/27 offering or programme eligibility.',
           'Four public programme guidance pages cover Computing and DSAI. They are not substituted for inaccessible PRDs.',
           '12 service pages cover scholarships, undergraduate halls, health appointments, clinics, IT, orientation and Library loans/hours/regulations.',
           'Service snapshots remain undated unless explicitly versioned. Opening hours, deadlines and eligibility must be read with their stated dates and groups.', '',
           '## Date and source checks','',
           'The Library student handbook returned by the old public PDF link explicitly says 2012/13. It is preserved locally but excluded from active retrieval.',
           'It was replaced with the Library public web pages; search-engine crawl dates were not treated as document publication dates.',
           'The original 2026/27 university handbook and all ten registration guides match today\'s public PDF bytes.',
           'Preparation, registration schedule and academic-unit directory have matching cleaned text.',
           '18 saved FAQ articles could not be compared automatically: the live server returned a JavaScript application without the article body.',
           'Those original articles remain with unconfirmed capture dates; do not claim their contents were freshly verified. Strict year queries exclude undated FAQs.',
           '2024/25 and 2025/26 handbooks are intentionally historical. September 2027 admissions pages are labelled 2027/28 and cannot answer 2026/27-specific requests.', '',
           '## Unresolved public links','']
 for row in report['unresolved']:
  lines += [f"- Programme {row['programme_code']}: {row.get('error','review needed')}. Official link: {row['requested_url']}"]
 lines += ['', 'DSAI\'s linked PRD location is an intranet and was not crawled. No login, authenticated student data, private Library database or enrolment endpoint was used.',
           'Faculties and schools have broad information coverage from the earlier collection. Full PRDs and subject forms for every PolyU programme/cohort are still not covered.', '',
           '## Use and handoff','',
           'Use the prebuilt index in data/policy_index.sqlite. Examples and integration contract are in README.md.',
           'Run python -X utf8 scripts/check_extended_resources.py for the new development checks.',
           'Share output/part1_handoff.zip with teammates. Scores are retrieval relevance, not confidence or eligibility decisions.', '']
 (folder/'COLLECTION_README.md').write_text('\n'.join(lines),encoding='utf-8')
 print('Saved extended_coverage.json and COLLECTION_README.md')

if __name__=='__main__': main()
