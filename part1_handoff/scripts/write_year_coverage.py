"""Write auditable year coverage and examples without changing historical tests."""
from collections import Counter
import json
import csv
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from policy_rag.retrieve import PolicyRetriever


def main():
    rows=json.loads((ROOT/'files/year_specific/download_manifest.json').read_text(encoding='utf-8'))
    verified=[r for r in rows if r['status']=='downloaded']
    extended=json.loads((ROOT/'files/extended_resources/download_manifest.json').read_text(encoding='utf-8')) if (ROOT/'files/extended_resources/download_manifest.json').exists() else []
    with (ROOT/'data/sources.csv').open(encoding='utf-8-sig',newline='') as f:
        all_programmes=[r for r in csv.DictReader(f) if r['source_type']=='programme_information']
    coverage=dict(added_source_counts=dict(Counter(r['source_type'] for r in verified)),
                  programme_entry_years=sorted(set(r['entry_year'] for r in verified if r['source_type']=='programme_information')),
                  policy_academic_years=['2024/25','2025/26','2026/27'],
                  programme_academic_years=sorted({r['academic_year'] for r in all_programmes}),
                  programme_page_count=len(all_programmes),
                  distinct_programme_codes=len({r['programme'] for r in all_programmes}),
                  programme_entry_term_counts=dict(Counter(r['entry_term']+' '+r['entry_year'] for r in all_programmes)),
                  failed_or_unverified_requests=sum(r['status']!='downloaded' for r in rows),
                  extended_source_counts=dict(Counter(r['source_type'] for r in extended if r['status']=='downloaded')),
                  prd_2026_27_programme_codes=sorted({r['programme_code'] for r in extended if r['status']=='downloaded' and r['source_type']=='programme_requirements'}),
                  limitations=['September 2026 admissions versions were unavailable. January 2027 pages separately cover that entry term in 2026/27; do not infer September 2026 cohort applicability. Selected 2026/27 PRDs provide partial coverage.',
                               'Admissions pages are not full cohort PRDs. Derived faculty lists compile the verified downloaded subset.',
                               'Academic year, calendar entry year, admission cohort and capture date are distinct metadata.'])
    (ROOT/'data/year_coverage.json').write_text(json.dumps(coverage,indent=2),encoding='utf-8')
    os.environ.setdefault('HF_HUB_OFFLINE','1')
    retriever=PolicyRetriever()
    examples={
        'year_programme_example':retriever.search('How many credits are required for Metaverse Technology for September 2027 entry?',method='hybrid'),
        'year_policy_example':retriever.search('What are the subject withdrawal rules?',academic_year='2025/26',knowledge_domain='policy',method='hybrid'),
        'year_missing_example':retriever.search('What are the credits for programme 61038 in 2023/24?',method='hybrid'),
    }
    for name,result in examples.items():
        (ROOT/'data'/f'{name}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved year coverage report and dated/missing-year query examples.')


if __name__=='__main__':
    main()
