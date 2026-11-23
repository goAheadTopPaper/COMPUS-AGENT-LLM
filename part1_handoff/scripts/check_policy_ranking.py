"""Regression checks for subject/programme withdrawal intent across handbook years."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from policy_rag.retrieve import PolicyRetriever


def main():
    retriever=PolicyRetriever()
    cases=[]
    variants=[
        ('What are the subject withdrawal rules?','subject_withdrawal'),
        ('How can I withdraw from a single course after the deadline?','subject_withdrawal'),
        ('How do I withdraw from my whole programme?','programme_withdrawal'),
        ('What is the procedure for withdrawal of study?','programme_withdrawal'),
    ]
    for year in ['2024/25','2025/26','2026/27']:
        for query,topic in variants:
            result=retriever.search(query,academic_year=year,knowledge_domain='policy',method='hybrid')
            assert result['results'], f'No results: {year} / {query}'
            assert all(r['academic_year']==year and r['policy_topic']==topic for r in result['results']), 'Wrong policy topic or year'
            if topic=='subject_withdrawal':
                assert 'Withdrawal of Subjects' in result['results'][0]['citation']['section']
                assert 'commencement of the examination period' in ' '.join(result['results'][0]['text'].split())
                assert 'refunded' in result['results'][0]['text']
            else:
                assert 'Withdrawal of Study' in result['results'][0]['citation']['section']
            cases.append(dict(query=query,academic_year=year,expected_topic=topic,first_citation=result['results'][0]['citation'],
                              count=len(result['results']),passed=True))
    comparison=retriever.search('What is the difference between subject withdrawal and programme withdrawal?',academic_year='2025/26',method='hybrid')
    assert {r['policy_topic'] for r in comparison['results']}=={'subject_withdrawal','programme_withdrawal'}, 'Comparison lost one policy type'
    ambiguous=retriever.search('What are the withdrawal rules?',academic_year='2025/26',method='bm25')
    assert ambiguous['requires_policy_clarification'], 'Ambiguous withdrawal scope was not flagged'
    result=dict(status='passed',cases=cases,comparison_topics=sorted({r['policy_topic'] for r in comparison['results']}),
                ambiguous_scope_flagged=True,limitations='Development regression checks; intent ranking is a transparent heuristic, not an answer-quality guarantee.')
    (ROOT/'data/policy_ranking_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Policy ranking PASSED: 12 year/scope cases; both withdrawal types retained for comparisons; ambiguous scope flagged.')


if __name__=='__main__':
    main()
