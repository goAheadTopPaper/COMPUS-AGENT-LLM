"""Validate scope separation, metadata and representative academic-unit searches."""
import json
import os
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from policy_rag.retrieve import PolicyRetriever


def main():
    retriever = PolicyRetriever()
    chunks = [c for c,_,_,_ in retriever.records]
    info = [c for c in chunks if c.get('source_type') == 'academic_unit_information']
    units = {c['unit'] for c in info if c['unit']}
    assert len(units) == 39, f'Expected all 39 academic units, got {len(units)}'
    assert all(c['source_type']=='academic_unit_information' for c in info)
    assert all(c['academic_year']=='not_specified' for c in info), 'Do not invent policy years for faculty pages'
    manifest = json.loads((ROOT / 'files/faculty wise rules/download_manifest.json').read_text(encoding='utf-8'))
    excluded = {r['file_path'] for r in manifest if r['status']!='downloaded'}
    assert not excluded.intersection(c['file_path'] for c in chunks)
    policy = retriever.search('Can I withdraw from a subject after the deadline?',method='hybrid')
    assert policy['knowledge_domain']=='policy'
    assert policy['results'] and all(r['knowledge_domain']=='policy' for r in policy['results'])
    tests = [
        ('How can I contact the Department of Computing?', 'Department of Computing','Contact'),
        ('What taught postgraduate programmes does the Faculty of Business offer?', 'Faculty of Business','Programmes'),
        ('What taught postgraduate programmes does FCMS offer?', 'Faculty of Computer and Mathematical Sciences','Programmes'),
        ('How can I contact the School of Hotel and Tourism Management?', 'School of Hotel and Tourism Management','Contact'),
        ('Tell me about PolyU Design and its school.', 'School of Design','Overview'),
        ('What postgraduate programmes are offered by the Faculty of Engineering?', 'Faculty of Engineering','Programmes'),
    ]
    details = []
    for query,unit,expected_page_type in tests:
        response = retriever.search(query,knowledge_domain='academic_information',unit=unit,method='hybrid',top_k=5)
        assert response['results'], f'No results for {unit}'
        assert all(r['unit']==unit for r in response['results'])
        assert all(r['knowledge_domain']=='academic_information' for r in response['results'])
        hit = any(r['page_type']==expected_page_type for r in response['results'])
        assert hit, f'Expected {expected_page_type} page in top 5 for {unit}'
        assert response['results'][0]['page_type']==expected_page_type, f'Wrong first page category for {unit}'
        assert all(r['page_type']==expected_page_type for r in response['results']), f'Unrelated page-category padding for {unit}'
        details.append(dict(query=query,unit_filter=unit,expected_page_type=expected_page_type,hit_at_5=hit,
                            evidence_ids=[r['evidence_id'] for r in response['results']]))
    fcms = retriever.search('What taught postgraduate programmes does FCMS offer?',knowledge_domain='academic_information',
                            unit='Faculty of Computer and Mathematical Sciences',method='hybrid')
    expected_codes = {'09002','09003','63024','63029','63031','63032','61030','61036','61038','61039','61040','62027','62037'}
    first = fcms['results'][0]
    assert first['complete_source_text'], 'FCMS list is still split'
    assert set(first['programme_codes']) == expected_codes, 'Some FCMS programme codes are missing'
    pairs = re.findall(r'([^\n]+)\nProgramme Code:\s*(\d{5})',first['text'])
    assert {code for name,code in pairs if name.startswith(('Master','Doctor'))} == expected_codes, 'Programme names and codes are no longer paired'
    for phrase in ['Your browser is not','What are you looking for?','Internal Document Search','Site Search','We use Cookies']:
        assert all(phrase not in c['text'] for c in info), f'UI boilerplate survived extraction: {phrase}'
    assert all('News & Events' not in r['text'] for r in fcms['results'])
    auto = retriever.search('Which faculties and departments does PolyU have?',method='bm25')
    assert auto['knowledge_domain']=='academic_information'
    assert not retriever.search('test',unit='Nonexistent Academic Unit',knowledge_domain='academic_information',method='bm25')['results']
    report = dict(status='passed',indexed_units=len(units),faculty_passages=len(info),
                  quarantined_sources=len(excluded),tests=details,
                  fcms_complete_listing=dict(first_result_page_type=first['page_type'],programme_codes=sorted(expected_codes),
                                             programme_count=len(expected_codes),complete_source_text=True),
                  limitations='Development integration checks; not a held-out answer-quality benchmark.')
    (ROOT / 'data/faculty_integration_checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'Faculty integration PASSED: {len(units)} units; domain separation; metadata filters; {len(tests)} representative searches.')


if __name__ == '__main__':
    main()
