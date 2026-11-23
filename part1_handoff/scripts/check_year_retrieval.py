"""Check dated evidence, missing-year behaviour and programme-specific routing."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from policy_rag.retrieve import PolicyRetriever


def main():
    retriever=PolicyRetriever()
    reports=[]
    for year in ['2024/25','2025/26','2026/27']:
        result=retriever.search('What are the subject withdrawal rules?',academic_year=year,knowledge_domain='policy',method='hybrid')
        assert result['results'] and all(r['academic_year']==year for r in result['results']), 'Cross-year policy contamination'
        assert all(r['source_type']=='handbook' for r in result['results']), 'Undated FAQ should not be proof of a specific year'
        reports.append(dict(query=result['query'],year=year,status='passed'))
    programme=retriever.search('How many credits are required for Metaverse Technology for September 2027 entry?',method='hybrid')
    assert programme['resolved_programme_code']=='61038'
    assert programme['results'] and all(r['entry_year']=='2027' and r['academic_year']=='2027/28' for r in programme['results'])
    assert all(r['programme_code']=='61038' for r in programme['results'])
    assert programme['results'][0]['programme_section']=='Credit Required for Graduation'
    assert '31' in programme['results'][0]['text']
    assert all(r['programme_section'] in {'Credit Required for Graduation','Curriculum','Summary'} for r in programme['results'])
    details=[c for c,_,_,_ in retriever.records if c.get('source_type')=='programme_information']
    for forbidden in ['View Other Programmes','APSS School Talk Series','Our Faculties and Schools','Programme by A-Z']:
        assert all(forbidden not in c['text'] for c in details), f'Programme recommendations/promotions remain: {forbidden}'
    fees=retriever.search('What are the tuition fees for programme 61038 for September 2027 entry?',method='hybrid')
    assert fees['results'] and all(r['programme_section']=='Tuition Fee' for r in fees['results'])
    summary=retriever.search('What is the duration for programme 61038 for September 2027 entry?',method='hybrid')
    assert summary['results'] and summary['results'][0]['programme_section']=='Summary'
    assert '1 year (Full-time)' in summary['results'][0]['text'] and 'Application Deadline' in summary['results'][0]['text']
    assert not programme['programme_requirements_coverage'], 'An admissions page is not a cohort PRD'
    missing=retriever.search('What are the credits for programme 61038 in 2023/24?',method='hybrid')
    assert not missing['results'] and missing['status']=='no_year_specific_evidence'
    assert '2027/28' in missing['available_academic_years']
    unavailable=retriever.search('What are the subject withdrawal rules?',academic_year='2023/24',knowledge_domain='policy',method='bm25')
    assert not unavailable['results']
    listing=retriever.search('What programmes does FCMS offer for 2027 entry?',entry_year=2027,
                             knowledge_domain='academic_information',unit='Faculty of Computer and Mathematical Sciences',method='hybrid')
    assert listing['results'] and all(r['source_type']=='programme_catalogue' for r in listing['results'])
    assert all(r['entry_year']=='2027' for r in listing['results'])
    normal=retriever.search('What are the subject withdrawal rules?',academic_year='2026/2027',knowledge_domain='policy',method='bm25')
    assert normal['year_filters']['academic_year']=='2026/27'
    try:
        retriever.search('Withdrawal rules in 2025/26',academic_year='2026/27',method='bm25')
    except ValueError:
        pass
    else:
        raise AssertionError('Conflicting question/filter years were accepted silently')
    report=dict(status='passed',policy_years=['2024/25','2025/26','2026/27'],programme_entry_years=[2027],
                checks=reports,programme_query=programme,missing_year_query=missing,year_listing=listing,
                limitations='Development tests; programme information is a snapshot of admissions pages, not a complete historical PRD collection.')
    (ROOT/'data/year_retrieval_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Year retrieval PASSED: three policy years; 2027 programme details/listing; exact code and year; missing-year rejection; PRD distinction.')


if __name__=='__main__':
    main()
