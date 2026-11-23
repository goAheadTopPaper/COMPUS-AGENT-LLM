"""Run real-corpus integrity checks and report development-set retrieval metrics."""
from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from policy_rag.retrieve import PolicyRetriever


def main():
    records = [json.loads(line) for line in (ROOT / 'data/documents.jsonl').read_text(encoding='utf-8').splitlines()]
    faqs = [r for r in records if r['source_type'] == 'faq']
    assert len(faqs) == 18, 'Expected all 18 FAQ answers'
    for faq in faqs:
        assert len(faq['text']) > len(faq['title']) + 40, f'FAQ body missing: {faq["source_id"]}'
        assert 'Recent Articles' not in faq['text'] and 'Helpful?' not in faq['text'], 'FAQ navigation leaked into body'
    chunks = [json.loads(line) for line in (ROOT / 'data/chunks.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len({c['chunk_id'] for c in chunks}) == len(chunks)
    assert {r['source_id'] for r in records} == {c['source_id'] for c in chunks}, 'Source disappeared in chunking'
    assert all(c['citation']['source_url'].startswith('https://') for c in chunks)
    retriever = PolicyRetriever()
    assert not retriever.search('zzzxxyyqq',method='bm25')['results'], 'Unknown lexical terms should not return arbitrary BM25 results'
    results = retriever.search('Chinese Cantonese Putonghua language requirements', student_type='taught_postgraduate',top_k=50)
    assert not any(r['student_type'] in {'undergraduate','full_time_undergraduate'} for r in results['results'])
    results = retriever.search('Cantonese Putonghua', admission_cohort='2026/27',top_k=50)
    assert not any(r['source_id'] == 'polyu_registration_faq_q23' for r in results['results'])
    first = chunks[0]['chunk_id']
    assert any(x['evidence_id'] == first for x in retriever.context(first))
    # These are development/smoke cases, NOT a held-out benchmark.
    cases = [
        ('Can I drop a subject after the Add/Drop Period?', ['polyu_registration_faq_q32']),
        ('Can I drop subjects through Canvas?', ['polyu_registration_faq_q31']),
        ('How can I check my registered subjects?', ['polyu_registration_faq_q30']),
        ('What happens to subject registration after eligibility to graduate is confirmed?', ['polyu_registration_faq_q29']),
        ('Why does my subject shopping cart exceed the programme maximum credits?', ['polyu_registration_faq_q24']),
        ('I do not meet prerequisite corequisite exclusion requirements. What should I do?', ['polyu_registration_faq_q20','polyu_registration_guide_10']),
        ('Is there a limit on retaking a failed subject?', ['polyu_registration_faq_q16']),
        ('How do I retake failed subjects?', ['polyu_registration_faq_q15','polyu_registration_guide_07']),
        ('Does a waitlist guarantee a place in class?', ['polyu_registration_guide_08']),
        ('Can I change my subject group if there are no vacancies?', ['polyu_registration_guide_06','polyu_registration_guide_10']),
        ('Will mock subject registration be carried over to actual registration?', ['polyu_registration_preparation','polyu_registration_guide_04']),
        ('How do I check my earliest commencing time?', ['polyu_registration_guide_02','polyu_registration_preparation']),
    ]
    report = {'dataset_type':'development_smoke_cases_not_held_out', 'structural_checks':'passed', 'methods':{}}
    for method in ['bm25','vector','hybrid']:
        details = []
        start = time.perf_counter()
        for query,expected in cases:
            result = retriever.search(query,method=method)
            ids = [r['source_id'] for r in result['results']]
            ranks = [i+1 for i,x in enumerate(ids) if x in expected]
            details.append(dict(query=query, expected_source_ids=expected, retrieved_source_ids=ids,
                                hit_at_5=bool(ranks), reciprocal_rank=1/min(ranks) if ranks else 0))
        report['methods'][method] = dict(hit_at_5=sum(d['hit_at_5'] for d in details)/len(details),
            mrr_at_5=sum(d['reciprocal_rank'] for d in details)/len(details),
            average_ms=(time.perf_counter()-start)*1000/len(details), cases=details)
    (ROOT / 'data/retrieval_checks.json').write_text(json.dumps(report,indent=2), encoding='utf-8')
    print('Corpus, FAQ extraction, citation, filtering and context checks: PASSED')
    for method,data in report['methods'].items():
        print(f'{method}: development Hit@5={data["hit_at_5"]:.1%}, MRR@5={data["mrr_at_5"]:.3f}')
    print('Saved data/retrieval_checks.json. Add independently labelled held-out cases before making research claims.')


if __name__ == '__main__':
    main()
