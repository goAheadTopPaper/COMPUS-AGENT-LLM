"""Extract the catalogued local files and create traceable retrieval passages."""
import csv
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'


def write_jsonl(path, records):
    path.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in records), encoding='utf-8')


def normalize(text):
    text = text.replace('\u00a0', ' ').replace('\x00', '').replace('\u00ad', '')
    text = re.sub(r'[\ue000-\uf8ff]', '', text)
    return '\n'.join(re.sub(r'[ \t]+', ' ', line).strip() for line in text.splitlines() if line.strip())


def policy_topic(heading):
    if re.search(r'withdrawal of subjects?|subject withdrawal|drop a subject after',heading,re.I):
        return 'subject_withdrawal'
    if re.search(r'withdrawal of study|programme withdrawal|program withdrawal',heading,re.I):
        return 'programme_withdrawal'
    if re.search(r'add/drop|add / drop',heading,re.I):
        return 'subject_registration_adjustment'
    return ''


def academic_text(tree,source):
    """Keep body content while removing embedded Sitecore UI/news components."""
    ui = re.compile(r'(?:^|\s)(?:old-browser|cookie[^\s]*|site-search[^\s]*|search-popup[^\s]*|search-panel[^\s]*|search-overlay[^\s]*)(?:\s|$)',re.I)
    for node in list(tree.iter()):
        if node.getparent() is None:
            continue
        cls = node.get('class') or ''
        if node.tag in {'nav','header','footer','button','form'} or ui.search(cls):
            node.drop_tree()
        elif 'ITS_' in cls and re.search(r'news|events',cls,re.I):
            node.drop_tree()
    for node in tree.xpath('//p|//li|//h1|//h2|//h3|//h4|//tr|//br|//div[contains(@class,"course-blk__main")]'):
        node.text = '\n' + (node.text or '')
        node.tail = '\n' + (node.tail or '')
    for node in tree.xpath('//td|//th'):
        node.tail = ' | ' + (node.tail or '')
    main = tree.xpath('//main|//*[@role="main"]')
    text = normalize((main[0] if main else tree).text_content())
    if source['page_type'] == 'Directory':
        text = text.split('Start main content',1)[-1].split('Sign up',1)[0]
    # Some sites embed common UI inside <main> without a shared CSS class.
    text = re.split(r'Your browser is not the latest version\.|What are you looking for\?|We use Cookies to give you a better experience',text, maxsplit=1)[0]
    lines = [line for line in text.splitlines() if line.strip() not in {'Site Search','Internal Document Search','Open Site Search Popup','Skip to main content','Start main content'}]
    if source.get('source_type')=='programme_information':
        lines=[line for line in lines if line.strip() not in {'About Programme','How to Apply'}]
    return normalize(source['title'] + '\n' + '\n'.join(lines))


def programme_records(tree,source):
    """Extract the main programme article and retain its field-level provenance."""
    articles=tree.xpath('//article[contains(@class,"node--prog-detail-")]')
    if not articles:
        raise ValueError(f'Main programme article missing: {source["file_path"]}')
    article=deepcopy(articles[0])
    # These siblings/widgets contain links to other programmes and unrelated
    # admissions events. Keep the actual application deadline block intact.
    remove={'other-prog-container','other-prog-wrapper','whats-new-container','basic-info-wrapper','programme-nav','prog-nav'}
    for node in list(article.iter()):
        if node.getparent() is not None and remove.intersection((node.get('class') or '').split()):
            node.drop_tree()
    academic_text(article,source)  # shared boilerplate cleanup and block boundaries
    allowed={'Aims & Characteristics','Recognition & Prospects','Curriculum',
             'Credit Required for Graduation','Programme Leader(s)','Subject Area',
             'Entrance Requirements','Enquiries','Other Information','Tuition Fee',
             'Additional Documents Required'}
    records=[]
    fields=[]
    prefix=f'{source["title"]}\nProgramme Code: {source["programme"]}\nEntry: {source["entry_term"]} {source["entry_year"]}\n'
    for label in article.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," field__label ")]'):
        heading=normalize(label.text_content())
        parent=label.getparent()
        if (heading not in allowed and source.get('student_type')!='undergraduate') or parent is None:
            continue
        if any(previous is parent or previous in parent.iterancestors() for previous in fields):
            continue
        text=normalize(parent.text_content())
        if len(text)<=len(heading):
            continue
        record=dict(source,document_id=f'{source["source_id"]}_section_{len(records):02}',
                    pdf_page=None,printed_page=None,section=heading,programme_section=heading,text=prefix+text)
        records.append(record)
        fields.append(parent)
    for node in fields:
        if node.getparent() is not None:
            node.drop_tree()
    summary=academic_text(article,source)
    records.insert(0,dict(source,document_id=f'{source["source_id"]}_summary',pdf_page=None,printed_page=None,
                          section='Programme summary and application deadlines',programme_section='Summary',text=summary))
    if len(records)<2:
        raise ValueError(f'Programme detail fields missing: {source["file_path"]}')
    return records


def programme_blocks(text):
    """Keep each name with its following programme-code line."""
    blocks = []
    for line in text.splitlines():
        if re.search(r'\bProgramme\s+Code\s*:',line,re.I) and blocks:
            blocks[-1] += '\n' + line
        elif line.strip():
            blocks.append(line)
    return blocks


def split_programme_list(text,size=800):
    # Short lists remain complete in one passage. Long lists split at intact
    # line/card boundaries; a name/code pair is never cut by a word window.
    blocks = programme_blocks(text)
    output,group,count = [],[],0
    for block in blocks:
        words = len(block.split())
        if group and count+words > size:
            output.append('\n'.join(group))
            group,count = [],0
        group.append(block)
        count += words
    if group:
        output.append('\n'.join(group))
    return output


def html_records(source, path):
    from lxml import html
    raw = path.read_bytes()
    # Browser-saved pages are UTF-8; downloaded server snapshots declare their own encoding.
    tree = html.fromstring(raw if source.get('knowledge_domain') in {'academic_information','student_services'} else raw.decode('utf-8-sig'))
    for node in tree.xpath('//script|//style|//noscript|//svg'):
        node.drop_tree()
    if source.get('source_type')=='programme_information':
        return programme_records(tree,source)
    if source.get('knowledge_domain') in {'academic_information','student_services'}:
        text = academic_text(tree,source)
    elif source['source_type'] == 'faq':
        nodes = tree.xpath('//*[@id="article_TOC"]')
        if not nodes:
            raise ValueError(f'FAQ answer body missing: {path.name}')
        for node in nodes[0].xpath('.//br|.//div|.//p|.//li'):
            node.tail = '\n' + (node.tail or '')
        text = source['title'] + '\n' + nodes[0].text_content()
    else:
        # Add block boundaries before taking text; preserve table cell relations.
        for node in tree.xpath('//br|//p|//li|//h1|//h2|//h3|//h4|//tr'):
            node.text = '\n' + (node.text or '')
            node.tail = '\n' + (node.tail or '')
        for node in tree.xpath('//th|//td'):
            node.tail = ' | ' + (node.tail or '')
        text = tree.text_content()
        start = 'Preparation for Subject Registration' if source['source_type'] == 'procedure' else 'Subject Registration Schedule for 2026/27 Semester One'
        if start not in text:
            raise ValueError(f'Main-content marker missing: {path.name}')
        text = text.split(start, 1)[1].split('Privacy Policy Statement', 1)[0]
        text = start + '\n' + text
    text = normalize(text)
    if len(text) < 50:
        raise ValueError(f'Extracted body suspiciously short: {path.name}')
    return [dict(source, document_id=source['source_id'], pdf_page=None,
                 printed_page=None, section=source['title'], text=text)]


def pdf_records(source, path):
    from pypdf import PdfReader
    output = []
    section = source['title']
    subsection=''
    for number, page in enumerate(PdfReader(path).pages, 1):
        text = normalize(page.extract_text() or '')
        if not text:
            continue
        lines = text.splitlines()
        printed = next((int(line) for line in lines[:2] if re.fullmatch(r'\d{1,3}', line)), None)
        if source['source_type'] == 'handbook':
            # Chapter identifiers must match chapter titles, not numbered body
            # sentences (e.g. "1. Announcements made by the Education Bureau").
            chapter=r'^(?:1\.\s+How to Use|2\.\s+Introduction to the University|3\.\s+Access to Information|4\.\s+Enrolment and Student Records|5\.\s+Subject Registration|6\.\s+Assessment|7\.\s+Award and Certification|8\.\s+Tuition and Other Fees|9\.\s+Important Notes|10\.\s+Notes for Students|11\.\s+Regulations and Rules|12\.\s+Facilities and Services|Appendix\s+\d+\.)'
            headings = [line for line in lines if re.match(chapter,line,re.I)]
            if headings and number > 8:
                if section!=headings[0]:
                    subsection=''
                section = headings[0]
        parts=[(text,subsection)]
        if (source['source_type']=='handbook' and number>8) or (source['source_type']=='programme_requirements' and number>2):
            pattern=r'(?m)^\d{1,2}(?:\.\d{1,2}){0,2}\s+[A-Z][^\n]{2,110}$' if source['source_type']=='programme_requirements' else r'(?m)^[A-Z]\.\s+[A-Z][^\n]{1,115}$'
            matches=list(re.finditer(pattern,text))
            if matches:
                parts=[]
                if text[:matches[0].start()].strip():
                    parts.append((text[:matches[0].start()].strip(),subsection))
                for i,match in enumerate(matches):
                    end=matches[i+1].start() if i+1<len(matches) else len(text)
                    subsection=match.group(0).strip()
                    parts.append((text[match.start():end].strip(),subsection))
        for i,(body,subheading) in enumerate(parts):
            output.append(dict(source, document_id=f'{source["source_id"]}_p{number:03}_s{i:02}',
                               pdf_page=number,printed_page=printed,
                               section=section+(' / '+subheading if subheading else ''),
                               programme_section=subheading if source['source_type']=='programme_requirements' else '',
                               policy_subsection=subheading,policy_topic=policy_topic(subheading),
                               text=(source['title']+'\n'+body) if source['source_type'] in {'programme_requirements','subject_description','student_service'} else body))
    return output


def split_words(text, size=350, overlap=60):
    words = text.split()
    if len(words) <= size:
        return [text]
    return [' '.join(words[start:start+size]) for start in range(0, len(words), size-overlap)
            if start == 0 or len(words[start:]) > overlap]


def main():
    with (DATA / 'sources.csv').open(encoding='utf-8-sig', newline='') as stream:
        sources = list(csv.DictReader(stream))
    docs, audit = [], []
    for source in sources:
        path = ROOT / source['file_path']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source['sha256']:
            raise ValueError(f'Source changed; rebuild the catalogue first: {path.name}')
        records = pdf_records(source, path) if source['file_type'] == 'pdf' else html_records(source, path)
        docs.extend(records)
        audit.append({'source_id': source['source_id'], 'records': len(records),
                      'characters': sum(len(x['text']) for x in records)})
    chunks = []
    for doc in docs:
        # Covers and near-empty divider pages provide little retrieval evidence.
        if doc['source_type'] == 'handbook' and len(doc['text'].split()) < 20:
            continue
        size, overlap = (140,25) if doc.get('knowledge_domain') == 'academic_information' else (350,60)
        if doc.get('page_type') == 'ProgrammeDetails':
            # Preserve individual paragraphs/sections of a detailed programme page.
            size,overlap=300,50
        if doc['source_type'] in {'programme_requirements','subject_description','student_service','programme_guidance'}:
            size,overlap=350,60
        passages = split_programme_list(doc['text']) if doc.get('page_type') == 'Programmes' else split_words(doc['text'],size,overlap)
        for position, text in enumerate(passages):
            digest = hashlib.sha256(text.encode()).hexdigest()[:12]
            chunk = dict(doc, text=text, chunk_id=f'{doc["document_id"]}_{position:02}_{digest}',
                         word_count=len(text.split()), subject_codes=sorted(set(re.findall(r'\b[A-Z]{2,6}\d{4,5}[A-Z]?\b', text+(' '+doc['title'] if doc['source_type']=='subject_description' else '')))))
            chunk['citation'] = dict(title=doc['title'], source_url=doc['source_url'],
                                     pdf_page=doc['pdf_page'], printed_page=doc['printed_page'], section=doc['section'])
            chunk['warnings'] = []
            chunk['policy_topic']=doc.get('policy_topic') or (policy_topic(doc['title']) if doc.get('knowledge_domain')=='policy' else '')
            chunk['programme_codes'] = sorted(set(re.findall(r'\bProgramme\s+Code\s*:\s*(\d{5})',text,re.I)))
            chunk['complete_source_text'] = len(passages)==1 and not doc.get('programme_section') and doc['file_type']!='pdf'
            chunk['complete_section_text'] = len(passages)==1 and doc['file_type']!='pdf'
            if doc['file_type'] == 'pdf':
                chunk['warnings'].append('Page-based extraction: inspect neighbouring passages for conditions continuing across pages; screenshots not OCRed.')
            if doc['student_type'] in {'mixed', 'taught_programmes_mixed', 'not_specified'}:
                chunk['warnings'].append('Check student/cohort applicability in the quoted text; source-level label is not proof of eligibility.')
            if doc['source_type'] == 'schedule':
                chunk['warnings'].append('Archived schedule; not live timetable, vacancy or personal registration data.')
            if doc.get('knowledge_domain') == 'academic_information' and doc['source_type']=='academic_unit_information':
                chunk['warnings'].append('Academic-unit snapshot, not binding programme requirements. Verify entry year and cohort; historical and prospective information may coexist.')
            if doc.get('source_type')=='programme_information':
                chunk['programme_codes']=sorted(set(chunk['programme_codes']+[doc['programme']]))
                chunk['warnings'].append('Published admissions information for the stated entry term; not a cohort-specific PRD and not evidence of live subject availability.')
            if doc['source_type'] in {'programme_requirements','programme_guidance'}:
                chunk['programme_codes']=sorted(set(chunk['programme_codes']+[doc['programme']]))
                chunk['warnings'].append('Check exact intake/cohort and pathway conditions in the source; document academic year is a version label, not personal eligibility.')
            if doc['source_type']=='subject_description':
                chunk['warnings'].append('Undated public subject description: not proof of a 2026/27 offering or inclusion in a particular programme.')
            if doc['source_type']=='student_service':
                chunk['warnings'].append('Public service snapshot; check linked official page for changes, deadlines and student-group eligibility.')
            chunks.append(chunk)
    ids = [c['chunk_id'] for c in chunks]
    assert len(ids) == len(set(ids))
    assert all(c['citation']['source_url'] for c in chunks)
    write_jsonl(DATA / 'documents.jsonl', docs)
    write_jsonl(DATA / 'chunks.jsonl', chunks)
    (DATA / 'extraction_report.json').write_text(json.dumps({'sources': len(sources), 'records': len(docs), 'chunks': len(chunks), 'details': audit}, indent=2), encoding='utf-8')
    print(f'Extracted {len(sources)} sources -> {len(docs)} document/page records -> {len(chunks)} cited passages.')
    print('Saved data/documents.jsonl, data/chunks.jsonl, data/extraction_report.json')


if __name__ == '__main__':
    main()
