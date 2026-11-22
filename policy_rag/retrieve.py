"""Small persistent SQLite passage/vector store with BM25 and TF-IDF retrieval.

TF-IDF vectors are lexical vectors, NOT pretrained semantic embeddings.
Optional SentenceTransformer vectors can be added with build_index --model.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import sqlite3
import os

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / 'data' / 'policy_index.sqlite'
STOP = set('a an the is are was were be been to for of and or in on at by as it its i my me can could would should do does did what how when where which please you your with from this that'.split())


def tokens(text):
    # English corpus baseline. Chinese questions require the semantic extension.
    text=re.sub(r'\bpre[\s-]+requisites?\b','prerequisite',text,flags=re.I)
    text=re.sub(r'\bco[\s-]+requisites?\b','corequisite',text,flags=re.I)
    text=re.sub(r'\bcredits\b','credit',text,flags=re.I)
    return [t for t in re.findall(r'[a-z]+\d+[a-z\d]*|[a-z]+|\d+(?:/\d+)?', text.lower()) if t not in STOP]


def normalized(vector):
    norm = math.sqrt(sum(x*x for x in vector.values())) or 1
    return {k: v/norm for k, v in vector.items()}


def build_index(model_name=None):
    chunks = [json.loads(line) for line in (ROOT / 'data/chunks.jsonl').read_text(encoding='utf-8').splitlines() if line]
    counts = [Counter(tokens(c.get('faculty','') + ' ' + c.get('unit','') + ' ' + c['title'] + ' ' + c['section'] + ' ' + c['text'])) for c in chunks]
    df = Counter(term for count in counts for term in count)
    idf = {t: math.log((1+len(chunks))/(1+n))+1 for t,n in df.items()}
    vectors = [normalized({t: (1+math.log(n))*idf[t] for t,n in count.items()}) for count in counts]
    dense = [None] * len(chunks)
    if model_name:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        # Encode every token window rather than silently dropping policy exceptions
        # beyond an encoder's token limit. Mean-pool and normalize per passage.
        windows,owners = [],[]
        limit = min(int(model.max_seq_length),1024)-model.tokenizer.num_special_tokens_to_add(False)
        for owner,c in enumerate(chunks):
            text = c.get('unit','') + '\n' + c['title'] + '\n' + c['text']
            token_ids = model.tokenizer.encode(text,add_special_tokens=False,truncation=False,verbose=False)
            for start in range(0,max(1,len(token_ids)),max(1,limit-30)):
                windows.append(model.tokenizer.decode(token_ids[start:start+limit],skip_special_tokens=True))
                owners.append(owner)
                if start+limit >= len(token_ids):
                    break
        encoded = model.encode(windows,normalize_embeddings=True,show_progress_bar=True).tolist()
        pooled = [[0.0]*len(encoded[0]) for _ in chunks]
        for owner,vector in zip(owners,encoded):
            pooled[owner] = [a+b for a,b in zip(pooled[owner],vector)]
        dense = []
        for vector in pooled:
            norm = math.sqrt(sum(x*x for x in vector)) or 1
            dense.append([x/norm for x in vector])
    # Replace only this generated index, in a single transaction.
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS passages (id TEXT PRIMARY KEY, payload TEXT, counts TEXT, vector TEXT, dense TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
        conn.execute('DELETE FROM passages')
        conn.execute('DELETE FROM settings')
        conn.executemany('INSERT INTO passages VALUES (?,?,?,?,?)', [
            (c['chunk_id'], json.dumps(c,ensure_ascii=False), json.dumps(dict(count)), json.dumps(vector), json.dumps(embedding))
            for c,count,vector,embedding in zip(chunks,counts,vectors,dense)])
        settings = dict(n=len(chunks), df=dict(df), idf=idf,
                        avgdl=sum(sum(c.values()) for c in counts)/max(1,len(counts)), model=model_name,
                        schema_version=3,embedding_pooling='normalized_mean_token_windows',
                        domain_counts=dict(Counter(c.get('knowledge_domain','policy') for c in chunks)))
        conn.executemany('INSERT INTO settings VALUES (?,?)', [(k,json.dumps(v)) for k,v in settings.items()])
    print(f'Indexed {len(chunks)} passages in {DB_PATH.name}.')
    print('Vectors: ' + ('SentenceTransformer + TF-IDF' if model_name else 'TF-IDF lexical vectors; pretrained semantic embeddings not enabled'))


class PolicyRetriever:
    def __init__(self, db_path=DB_PATH):
        if not Path(db_path).is_file():
            raise FileNotFoundError('Build the index first: python -m policy_rag.retrieve --build')
        with sqlite3.connect(db_path) as conn:
            self.settings = {k:json.loads(v) for k,v in conn.execute('SELECT key,value FROM settings')}
            self.records = [(json.loads(p),json.loads(c),json.loads(v),json.loads(d))
                            for _,p,c,v,d in conn.execute('SELECT * FROM passages')]
        self.model = None
        self.programme_names={}
        for c,_,_,_ in self.records:
            if c.get('source_type')=='programme_information':
                name=c['title'].split(' - ',1)[-1].split(' | ',1)[0]
                short=re.sub(r'^(Master of Science(?: Scheme)? in|Master of|Doctor of|Postgraduate Diploma in)\s+','',name,flags=re.I)
                self.programme_names.setdefault(short.casefold(),set()).add(c['programme'])

    @staticmethod
    def allowed(c, student_type, academic_year, programme_code, admission_cohort):
        if academic_year and c['academic_year'] not in {'', 'not_specified', academic_year}:
            return False
        if programme_code and c['programme'] not in {'', 'not_programme_specific', programme_code}:
            return False
        if student_type:
            known = c['student_type']
            if student_type in {'undergraduate','full_time_undergraduate','part_time_undergraduate'} and known in {'postgraduate','taught_postgraduate','research_postgraduate'}:
                return False
            if student_type in {'postgraduate', 'taught_postgraduate', 'research_postgraduate'} and known in {'undergraduate', 'full_time_undergraduate', 'part_time_undergraduate'}:
                return False
            if student_type=='research_postgraduate' and known=='taught_postgraduate':
                return False
            if student_type=='taught_postgraduate' and known=='research_postgraduate':
                return False
            if student_type == 'research_postgraduate' and known == 'taught_programmes_mixed':
                return False
            if student_type == 'part_time_undergraduate' and known == 'full_time_undergraduate':
                return False
        cohort = c['cohort']
        if admission_cohort and cohort not in {'', 'not_specified'}:
            years = re.findall(r'\b(20\d{2})/', cohort)
            requested = re.match(r'^(20\d{2})/', admission_cohort)
            if requested and len(years) == 2 and 'to' in cohort:
                if not int(years[0]) <= int(requested.group(1)) <= int(years[1]):
                    return False
            elif admission_cohort != cohort:
                return False
        return True

    def search(self, query, top_k=5, method='hybrid', student_type=None, academic_year=None, programme_code=None, admission_cohort=None, source_type=None, subject_codes=None, knowledge_domain='auto',faculty=None,unit=None,entry_year=None,strict_year=None,entry_term=None,admission_pathway=None):
        if method not in {'bm25','vector','hybrid','semantic'}:
            raise ValueError('method must be bm25, vector, hybrid or semantic')
        if not query.strip() or not 1 <= top_k <= 50:
            raise ValueError('Provide a nonempty query and top_k between 1 and 50')
        if student_type and student_type not in {'undergraduate','full_time_undergraduate','part_time_undergraduate','postgraduate','taught_postgraduate','research_postgraduate'}:
            raise ValueError('Unrecognized student_type; use the values documented in PART1_GUIDE.md')
        if knowledge_domain not in {'auto','policy','academic_information','student_services','all'}:
            raise ValueError('knowledge_domain must be auto, policy, academic_information, student_services or all')
        # JS identifiers are programme codes, never subject codes.
        query_subjects=[code for code in re.findall(r'\b(?:[A-Z]{2,6}\d{4,5}[A-Z]?|COMP\s+\d{4,5}[A-Z]?)\b',query.upper())
                        if not re.fullmatch(r'JS\d{4}',code)]
        if subject_codes is None and query_subjects:
            subject_codes=[re.sub(r'\s','',code) for code in query_subjects]
        ambiguous_programme_codes=[]
        if not programme_code:
            known_codes={c['programme'] for c,_,_,_ in self.records if c.get('source_type') in {'programme_information','programme_requirements'}}
            code_match=next((code for code in re.findall(r'\b\d{5}\b',query) if code in known_codes),None)
            name_matches=sorted((name for name in self.programme_names if len(name.split())>=2 and name in query.casefold()),key=len,reverse=True)
            if re.search(r'contact|e.?mail|phone|telephone|enquir',query,re.I):
                name_matches=[]
            explicit_code=re.search(r'programme\s*(?:code)?\s*[:#]?\s*(\d{5})\b',query,re.I)
            matched_codes=self.programme_names[name_matches[0]] if name_matches else set()
            if len(matched_codes)>1:
                ambiguous_programme_codes=sorted(matched_codes)
            programme_code=(explicit_code.group(1) if explicit_code else None) or code_match or (next(iter(matched_codes)) if len(matched_codes)==1 else None)
            jupas=re.search(r'\bJS\d{4}\b',query,re.I)
            if jupas:programme_code=jupas.group(0).upper()
        if programme_code:
            programme_code=str(programme_code).upper()
        if admission_pathway is None and (programme_code and programme_code.upper().startswith('JS')):
            if re.search(r'non.?jupas.*(?:AD.?HD|senior)|senior.year',query,re.I):admission_pathway='non-jupas-adhd-grad'
            elif re.search(r'non.?jupas',query,re.I):admission_pathway='non-jupas'
            elif re.search(r'\bjupas\b',query,re.I):admission_pathway='jupas'
            elif re.search(r'international',query,re.I):admission_pathway='international'
            elif re.search(r'mainland|\bjee\b|gaokao',query,re.I):admission_pathway='jee'
        mentioned_year=re.search(r'\b(20\d{2})\s*[/\-]\s*(20\d{2}|\d{2})\b',query)
        if academic_year is None and mentioned_year:
            academic_year=mentioned_year.group(1)+'/'+mentioned_year.group(2)[-2:]
        explicit_academic_year=academic_year is not None
        if academic_year is not None:
            match=re.fullmatch(r'(20\d{2})[/\-](20\d{2}|\d{2})',academic_year)
            if not match or (int(match.group(1))+1)%100 != int(match.group(2)[-2:]):
                raise ValueError('academic_year must be a consecutive year, e.g. 2026/27 or 2026/2027')
            academic_year=match.group(1)+'/'+match.group(2)[-2:]
            if mentioned_year and academic_year!=mentioned_year.group(1)+'/'+mentioned_year.group(2)[-2:]:
                raise ValueError('The academic year in the question conflicts with the academic_year filter')
        mentioned_entry=re.search(r'\b(20\d{2})\b',query) if re.search(r'entry|intake|admission',query,re.I) and not mentioned_year else None
        if entry_year is None:
            entry_year=int(mentioned_entry.group(1)) if mentioned_entry else None
        if entry_year is not None:
            entry_year=str(entry_year)
            if not re.fullmatch(r'20\d{2}',entry_year):
                raise ValueError('entry_year must be a four-digit year')
            if mentioned_entry and entry_year!=mentioned_entry.group(1):
                raise ValueError('The entry year in the question conflicts with the entry_year filter')
        term_match=re.search(r'\b(Jan(?:uary)?|Sept(?:ember)?)\s+20\d{2}\b',query,re.I)
        if entry_term is None:
            if term_match:entry_term=term_match.group(1)
        if entry_term:
            terms_by_name={'jan':'January','january':'January','sept':'September','september':'September'}
            if entry_term.casefold() not in terms_by_name:raise ValueError('entry_term must be January or September')
            entry_term=terms_by_name[entry_term.casefold()]
            if term_match and entry_term!=terms_by_name[term_match.group(1).casefold()]:
                raise ValueError('The entry term in the question conflicts with the entry_term filter')
        if strict_year is None:
            strict_year=explicit_academic_year or entry_year is not None
        domain = knowledge_domain
        if domain == 'auto':
            if source_type=='student_service' or re.search(r'\blibrary\b|\bborrow\b|\bscholarship|\baccommodation\b|\bhalls?\b|\bclinic\b|\bUHS\b|health service|medical appointment|\bcounselling\b|\bIT Help|\beduroam\b|\bPolyUWLAN\b|IT services|Canvas access|financial assistance|emergency financial|\bvisa\b|special needs|career advising|sports facilities',query,re.I):
                domain='student_services'
            elif source_type in {'academic_unit_information','programme_information','programme_requirements','subject_description','programme_guidance','programme_directory','research_programme_information'} or programme_code or subject_codes or re.search(r'\bMPhil\b|\bPhD\b|research postgraduate|\bJUPAS\b|undergraduate programme',query,re.I):
                domain = 'academic_information'
            elif re.search(r'withdraw|credit|prerequis|retak|exam|regist|waitlist|probation|plagiari|integrity|appeal|add.drop',query,re.I):
                domain = 'policy'
            elif faculty or unit or re.search(r'facult|department|school|contact|dean|programme|programs?|\bmsc\b|\bmba\b|\bfcms\b',query,re.I):
                domain = 'academic_information'
            else:
                domain = 'policy'
        # Keep existing no-year policy queries on the current handbook, while
        # explicit years require dated evidence rather than undated fallback.
        if academic_year is None and domain=='policy' and entry_year is None:
            academic_year='2026/27'
        # Small, auditable vocabulary bridge; the original question is preserved.
        query_expansions=[]
        preferred_policy_sections=[]
        if domain=='policy':
            intents=[
                (r'defer(?:ment)?\s+(?:of\s+)?stud|(?:pause|suspend|interrupt|break from).{0,30}stud', 'Deferment of Study'),
                (r'(?:illness|sick|injur|unable|cannot|miss).{0,65}(?:exam|assessment)|(?:exam|assessment).{0,65}(?:illness|sick|injur)', 'Late Assessment'),
                (r'(?:not pay|unpaid|non.payment|late payment|fail to pay).{0,35}(?:tuition|fees?)|(?:tuition|fees?).{0,35}(?:not paid|unpaid|overdue)', 'Non-payment of Fees'),
            ]
            for pattern,section_name in intents:
                if re.search(pattern,query,re.I):
                    preferred_policy_sections.append(section_name)
                    query_expansions.append(section_name)
            if re.search(r'appeal',query,re.I) and re.search(r'(?:subject|assessment) results?',query,re.I):
                query_expansions.append('Appeals against Decisions on Subject Results')
            if re.search(r'credit transfer',query,re.I) and re.search(r'apply|application|request',query,re.I):
                query_expansions.append('Application for Credit Transfer')
        if domain=='student_services' and re.search(r'\bUHS\b',query,re.I):
            query_expansions.append('University Health Service')
        scoring_query=query+' '+' '.join(query_expansions)
        terms = Counter(tokens(scoring_query))
        qvector = normalized({t:(1+math.log(n))*self.settings['idf'][t] for t,n in terms.items() if t in self.settings['idf']})
        dense_query = None
        if method == 'semantic' or (method == 'hybrid' and self.settings['model']):
            if not self.settings['model']:
                raise ValueError('Semantic embeddings are not built. Rebuild with --model MODEL_NAME_OR_LOCAL_PATH.')
            if self.model is None:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(self.settings['model'])
            dense_query = self.model.encode(scoring_query, normalize_embeddings=True).tolist()
        bm_scores, vec_scores, eligible = {}, {}, {}
        available_years=set()
        for c,counts,vector,dense in self.records:
            if domain != 'all' and c.get('knowledge_domain','policy') != domain:
                continue
            if faculty and faculty.casefold() != c.get('faculty','').casefold():
                continue
            if unit and c.get('unit','').casefold() != unit.casefold():
                continue
            if programme_code and c.get('programme') not in {'', 'not_programme_specific',programme_code}:
                continue
            if c.get('academic_year') not in {'','not_specified',None}:
                available_years.add(c['academic_year'])
            if strict_year and academic_year and c.get('academic_year')!=academic_year:
                continue
            if entry_year is not None and str(c.get('entry_year',''))!=entry_year:
                continue
            if entry_term and c.get('entry_term')!=entry_term:
                continue
            if admission_pathway and c.get('admission_pathway')!=admission_pathway:
                continue
            if programme_code and domain=='academic_information' and c.get('programme')!=programme_code:
                continue
            if not self.allowed(c,student_type,academic_year,programme_code,admission_cohort):
                continue
            if source_type and c['source_type'] != source_type:
                continue
            if subject_codes and not set(x.upper() for x in subject_codes).intersection(c['subject_codes']):
                continue
            key = c['chunk_id']
            eligible[key] = c
            dl = sum(counts.values())
            bm = 0.0
            for t in terms:
                tf = counts.get(t,0)
                if tf:
                    df = self.settings['df'][t]
                    weight = math.log(1+(self.settings['n']-df+0.5)/(df+0.5))
                    bm += weight * tf*2.5 / (tf + 1.5*(0.25+0.75*dl/self.settings['avgdl']))
            bm_scores[key] = bm
            vec_scores[key] = sum(a*b for a,b in zip(dense_query,dense)) if dense_query is not None else sum(v*vector.get(t,0) for t,v in qvector.items())
        def ranked(scores):
            return [key for key in sorted(scores, key=lambda k:(-scores[k],k)) if scores[key] > 0]
        if method == 'hybrid':
            # Reciprocal rank fusion avoids pretending BM25 and cosine share a scale.
            scores = Counter()
            for ranking in [ranked(bm_scores)[:50], ranked(vec_scores)[:50]]:
                for rank,key in enumerate(ranking,1):
                    scores[key] += 1/(60+rank)
        else:
            scores = bm_scores if method == 'bm25' else vec_scores
        preferred_page_type = None
        if domain == 'academic_information':
            if subject_codes:
                preferred_page_type='SubjectDescription'
            elif re.search(r'\bMPhil\b|\bPhD\b|research postgraduate',query,re.I) and not programme_code:
                preferred_page_type='ResearchProgrammes'
            elif programme_code:
                preferred_page_type='ProgrammeDetails'
            elif re.search(r'contact|e.?mail|phone|telephone|enquir',query,re.I):
                preferred_page_type = 'Contact'
            elif re.search(r'programmes?|programs?|courses?|degrees?|taught postgraduate|\bmsc\b|\bmba\b',query,re.I):
                preferred_page_type = 'Programmes'
            elif re.search(r'tell me about|overview|introduction|dean|head of',query,re.I):
                preferred_page_type = 'Overview'
        ranking = ranked(scores)
        if preferred_policy_sections:
            matches=[key for key in ranking if any(name.casefold() in eligible[key]['section'].casefold() for name in preferred_policy_sections)]
            ranking=matches+[key for key in ranking if key not in matches]
        if domain=='policy' and 'Appeals against Decisions on Subject Results' in query_expansions:
            matches=[key for key in ranking if re.search(r'Appeals against Decisions on Subject Results',eligible[key]['text'],re.I)]
            ranking=matches+[key for key in ranking if key not in matches]
        if domain=='policy' and 'Application for Credit Transfer' in query_expansions:
            matches=[key for key in ranking if re.search(r'Application for Credit Transfer',eligible[key]['text'],re.I)
                     and re.search(r'AR41c',eligible[key]['text'],re.I)]
            ranking=matches+[key for key in ranking if key not in matches]
        # A PRD is the preferred source for programme rules when the requested
        # version is present. Programme admissions fields remain the fallback.
        if programme_code and not subject_codes and domain=='academic_information':
            prds=[key for key in ranking if eligible[key].get('source_type')=='programme_requirements']
            if prds:
                preferred_page_type='ProgrammeRequirements'
        preferred_policy_topics=[]
        requires_policy_clarification=False
        if domain=='policy' and (re.search(r'withdraw',query,re.I) or (re.search(r'\bdrop\b',query,re.I) and re.search(r'after|deadline',query,re.I))):
            subject=bool(re.search(r'\bsubjects?\b|\bcourses?\b|\bmodules?\b',query,re.I))
            programme=bool(re.search(r'\bprogrammes? withdrawal\b|\bprograms? withdrawal\b|withdrawal of study|withdraw(?:al|ing)?\s+(?:from\s+)?(?:(?:my|the|a|an|whole|entire)\s+)*(?:programme|program|university|polyu|studies|study)\b',query,re.I))
            if subject:
                preferred_policy_topics.append('subject_withdrawal')
            if programme:
                preferred_policy_topics.append('programme_withdrawal')
            requires_policy_clarification=not(subject or programme)
        topic_matches=[key for key in ranking if eligible[key].get('policy_topic') in preferred_policy_topics]
        if topic_matches:
            ranking=topic_matches
        preferred = [key for key in ranking if eligible[key].get('page_type') == preferred_page_type] if preferred_page_type else []
        # When the requested page category exists, return its evidence rather
        # than padding the response with unrelated dean messages or home/news.
        if preferred:
            ranking = preferred
        preferred_service_evidence=None
        if domain=='student_services':
            named=[key for key in ranking if len(eligible[key]['title'].split(' | ')[0].split())>=3
                   and eligible[key]['title'].split(' | ')[0].casefold() in query.casefold()]
            if named:
                ranking=named
                preferred_service_evidence='named_service_page'
            if re.search(r'university health service|\bUHS\b',query,re.I) and re.search(r'eligible|eligibility|part.time|full.time|\bcan\b',query,re.I):
                # Prefer actual student eligibility clauses over health-topic
                # indexes. Keep the original source and contextual warnings.
                scoped=[key for key in ranked(scores) if re.search(r'full[\s-]*time\s+(?:PolyU\s+)?students',eligible[key]['text'],re.I)
                        and re.search(r'university health service|\bUHS\b',eligible[key]['text'],re.I)]
                if scoped:
                    ranking=sorted(scoped,key=lambda key:(not bool(re.search(r'UHS service.{0,130}\bonly\b',eligible[key]['text'],re.I)),-scores[key],key))
                    preferred_service_evidence='explicit_student_eligibility_clause'
            if re.search(r'counsell',query,re.I) and re.search(r'book|appointment',query,re.I):
                actionable=[key for key in ranking if re.search(r'counsell',eligible[key]['title'],re.I)
                            and re.search(r'(?:Email:|Phone:|Login the POSS)',eligible[key]['text'],re.I)]
                if actionable:
                    ranking=actionable+[key for key in ranking if key not in actionable]
                    preferred_service_evidence='appointment_contact_instructions'
        if preferred_page_type=='SubjectDescription':
            phrase=None
            if re.search(r'pre.?requis|co.?requis|exclusion',query,re.I):
                phrase=r'pre[\s-]*requisite|co[\s-]*requisite|exclusion'
            elif re.search(r'credit',query,re.I):
                phrase=r'credit\s+value'
            elif re.search(r'assess|exam|coursework',query,re.I):
                phrase=r'assessment\s+(?:methods|method)|continuous\s+assessment'
            if phrase:
                matching=[key for key in ranking if re.search(phrase,eligible[key]['text'],re.I)]
                if matching:
                    ranking=matching
        preferred_sections=[]
        if preferred_page_type=='ProgrammeRequirements' and re.search(r'credit|graduat',query,re.I):
            # Distinguish graduation credit requirements from the award category
            # called "Credit" and from GPA/assessment classification tables.
            matching=[key for key in ranking if re.search(r'application for graduation|graduation requirements|requirements for (?:graduation|award)|credit requirements|credits? required for graduation',eligible[key].get('programme_section',''),re.I)
                      and len(eligible[key]['text'].split())>60]
            if matching:
                ranking=matching
        if preferred_page_type=='ProgrammeDetails':
            if re.search(r'tuition|fees?|cost|charges?',query,re.I):
                preferred_sections+=['Tuition Fee']
            if re.search(r'credits?|core|electives?|curriculum',query,re.I):
                preferred_sections+=['Curriculum','Credit Required for Graduation','Summary'] if re.search(r'breakdown|core|elective|curriculum|distribution',query,re.I) else ['Credit Required for Graduation','Summary','Curriculum']
            if re.search(r'entrance|admission requirements?|eligib|documents?',query,re.I):
                preferred_sections+=['Entrance Requirements','Additional Documents Required','Summary']
            if re.search(r'deadline|duration|long|full.time|part.time',query,re.I):
                preferred_sections+=['Summary']
            preferred_sections=list(dict.fromkeys(preferred_sections))
            matching=[key for key in ranking if eligible[key].get('programme_section') in preferred_sections]
            if matching:
                # Include the best passage from each requested field before more
                # passages from the same field consume the evidence budget.
                groups=[[key for key in matching if eligible[key]['programme_section']==section] for section in preferred_sections]
                ranking=[group[i] for i in range(max(map(len,groups))) for group in groups if i<len(group)]
        results = []
        for key in ranking[:top_k]:
            c = eligible[key]
            warnings = list(c['warnings'])
            if c.get('source_type')=='faq' and not c.get('captured_at'):
                warnings.append('Saved FAQ capture date is unconfirmed; live JavaScript article content was not automatically reverified in the currency check.')
            if admission_cohort and c['cohort'] not in {'', 'not_specified', admission_cohort}:
                warnings.append(f'Cohort applicability requires review: source says {c["cohort"]}; requested {admission_cohort}.')
            results.append(dict(evidence_id=key, source_id=c['source_id'], text=c['text'], citation=c['citation'],
                                score=round(scores[key],6), student_type=c['student_type'], academic_year=c['academic_year'],
                                source_type=c['source_type'],knowledge_domain=c.get('knowledge_domain','policy'),
                                faculty=c.get('faculty',''),unit=c.get('unit',''),page_type=c.get('page_type',''),
                                programme_codes=c.get('programme_codes',[]),complete_source_text=c.get('complete_source_text',False),
                                programme_section=c.get('programme_section',''),complete_section_text=c.get('complete_section_text',False),
                                policy_topic=c.get('policy_topic',''),policy_subsection=c.get('policy_subsection',''),
                                captured_at=c.get('captured_at',''),warnings=warnings))
            results[-1].update(programme_code=c.get('programme',''),entry_year=c.get('entry_year',''),entry_term=c.get('entry_term',''),
                               cohort=c.get('cohort',''),year_basis=c.get('year_basis',''),admission_pathway=c.get('admission_pathway',''))
        return dict(query=query, method=method, vector_backend='sentence_transformer' if dense_query is not None else 'tfidf_lexical',
                    status='candidates_found' if results else ('no_year_specific_evidence' if strict_year else 'no_matching_evidence'),
                    knowledge_domain=domain,
                    year_filters=dict(academic_year=academic_year,entry_year=entry_year,entry_term=entry_term,strict_year=strict_year),
                    admission_pathway=admission_pathway,
                    requires_admission_pathway_clarification=bool(programme_code and not admission_pathway and len({c.get('admission_pathway') for c in eligible.values() if c.get('admission_pathway')})>1),
                    requires_entry_term_clarification=bool(programme_code and not entry_term and len({c.get('entry_term') for c in eligible.values() if c.get('entry_term')})>1),
                    available_academic_years=sorted(available_years),resolved_programme_code=programme_code,
                    requires_year_clarification=bool(programme_code and not explicit_academic_year and entry_year is None),
                    requires_programme_clarification=bool(ambiguous_programme_codes and not programme_code),
                    ambiguous_programme_codes=ambiguous_programme_codes,
                    preferred_page_type=preferred_page_type,
                    preferred_service_evidence=preferred_service_evidence,
                    query_expansions=query_expansions,preferred_policy_sections=preferred_policy_sections,
                    page_type_preference_applied=bool(preferred),
                    preferred_programme_sections=preferred_sections,
                    preferred_policy_topics=preferred_policy_topics,policy_topic_preference_applied=bool(topic_matches),
                    requires_policy_clarification=requires_policy_clarification,
                    programme_specific_coverage=any(c.get('programme')==programme_code for c in eligible.values()) if programme_code else False,
                    programme_requirements_coverage=any(c.get('source_type')=='programme_requirements' and c.get('programme')==programme_code for c in eligible.values()) if programme_code else False,
                    results=results,
                    limitations=['Retrieval ranks candidates; it does not decide answerability, validity or personal eligibility.',
                                 'Mixed-source passages may contain subgroup conditions. Check the text.',
                                 'Scores are relevance measures, not confidence probabilities.'])

    def context(self, evidence_id):
        """Return adjacent passage(s) from the same source for cross-page conditions."""
        records = [c for c,_,_,_ in self.records]
        position = next((i for i,c in enumerate(records) if c['chunk_id'] == evidence_id), None)
        if position is None:
            raise KeyError(evidence_id)
        source_id = records[position]['source_id']
        return [dict(evidence_id=c['chunk_id'],text=c['text'],citation=c['citation'])
                for c in records[max(0,position-1):position+2] if c['source_id'] == source_id]


def retrieve_evidence(query, **kwargs):
    return PolicyRetriever().search(query, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--model', help='Optional SentenceTransformer model ID or local path; first use may download weights')
    parser.add_argument('--query')
    parser.add_argument('--method', default='hybrid', choices=['bm25','vector','hybrid','semantic'])
    parser.add_argument('--student-type')
    parser.add_argument('--academic-year',help='Explicit year, e.g. 2026/27. Uses strict dated evidence by default.')
    parser.add_argument('--entry-year',type=int,help='Admission calendar year, e.g. 2027; distinct from academic year')
    parser.add_argument('--entry-term',choices=['January','September'],help='Keep January and September entry evidence separate')
    parser.add_argument('--admission-pathway',help='Exact pathway, e.g. jupas, non-jupas, non-jupas-adhd-grad, international, jee')
    parser.add_argument('--allow-undated',action='store_true',help='Allow undated background when an academic year is specified; does not confirm year applicability')
    parser.add_argument('--programme-code')
    parser.add_argument('--top-k', type=int, default=5)
    parser.add_argument('--domain', default='auto',choices=['auto','policy','academic_information','student_services','all'])
    parser.add_argument('--faculty',help='Exact faculty/school name, case insensitive')
    parser.add_argument('--unit',help='Exact academic unit name, case insensitive')
    parser.add_argument('--output', type=Path, help='Write UTF-8 JSON directly, avoiding PowerShell pipe encoding')
    parser.add_argument('--offline',action='store_true',help='Use cached model files without network requests')
    args = parser.parse_args()
    if args.offline:
        os.environ['HF_HUB_OFFLINE']='1'
    if args.build:
        build_index(args.model)
    elif args.query:
        result = retrieve_evidence(args.query, top_k=args.top_k, method=args.method, student_type=args.student_type, academic_year=args.academic_year, programme_code=args.programme_code,knowledge_domain=args.domain,faculty=args.faculty,unit=args.unit,entry_year=args.entry_year,entry_term=args.entry_term,admission_pathway=args.admission_pathway,strict_year=False if args.allow_undated else None)
        serialized = json.dumps(result,ensure_ascii=False,indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized + '\n', encoding='utf-8')
            print(f'Saved {args.output}')
        else:
            print(serialized)
    else:
        parser.error('Use --build or --query "your question"')


if __name__ == '__main__':
    main()
