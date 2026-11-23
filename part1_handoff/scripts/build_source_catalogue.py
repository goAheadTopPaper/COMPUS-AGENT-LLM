"""Build Step 2 metadata with Python's standard library.

Run: python scripts/build_source_catalogue.py
Edit data/source_metadata_overrides.csv to supply verified missing metadata.
Blank override cells preserve automatically recovered values.
"""
import csv
import hashlib
import html
import re
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

PROJECT = Path(__file__).resolve().parents[1]
DATA = PROJECT / 'data'
GUIDE_PAGE = 'https://www.polyu.edu.hk/ar/students-in-taught-programmes/registration-information/subject-registration/guides-for-subject-registration/'
GUIDE_BASE = 'https://www.polyu.edu.hk/ar/docdrive/polyu-students/subj-reg/'
# Session links checked against the official guide page on 2026-11-19.
GUIDE_TITLES = {
    '01': 'Access eStudent',
    '02': 'Preparation - Check subject registration records and start time',
    '03': 'Preparation - Search subject and class timetable',
    '04': 'Add Subject',
    '05': 'Drop Subject',
    '06': 'Change Class (Subject Group/Subject Component)',
    '07': 'Retake a Failed Subject',
    '08': 'Waitlisting for Subjects',
    '09': 'Indicate Interest in Service-Learning Subjects Requiring Selection',
    '10': 'Common Errors in Subject Registration',
}
FIELDS = [
    'source_id', 'file_path', 'file_type', 'title', 'source_url',
    'source_url_basis', 'publisher', 'source_type', 'academic_year',
    'student_type', 'programme', 'cohort', 'captured_at',
    'file_modified_at_utc', 'sha256', 'metadata_status', 'notes',
    'knowledge_domain', 'faculty', 'unit', 'page_type',
    'entry_year','entry_term','year_basis',
    'admission_pathway',
]
OVERRIDE_FIELDS = ['source_id', 'captured_at', 'academic_year', 'student_type', 'programme', 'cohort', 'notes']


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_record(selected):
    path = PROJECT / selected['file_path']
    content = path.read_bytes()
    row = dict.fromkeys(FIELDS, '')
    row.update(
        file_path=selected['file_path'], file_type=selected['file_type'],
        publisher='The Hong Kong Polytechnic University - Academic Registry',
        academic_year='not_specified', student_type='not_specified',
        programme='not_programme_specific', cohort='not_specified',
        file_modified_at_utc=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        sha256=hashlib.sha256(content).hexdigest(),
        knowledge_domain='policy',
    )
    notes = ['Original download date is unconfirmed; file modification time is not treated as capture date.']
    if selected['file_path'].startswith('files/schoolwide/'):
        manifest=json.loads((PROJECT/'files/schoolwide/download_manifest.json').read_text(encoding='utf-8'))
        item=next(r for r in manifest if r.get('file_path')==selected['file_path'] and r['status']=='downloaded')
        row.update(source_id='polyu_schoolwide_'+hashlib.sha256(item['source_url'].encode()).hexdigest()[:16],
                   title=item['title'],source_url=item['source_url'],source_url_basis='discovered from official catalogue or public service directory',
                   publisher='The Hong Kong Polytechnic University',source_type=item['source_type'],academic_year=item['academic_year'],
                   programme=item['programme_code'],captured_at=item['captured_at'],year_basis=item['year_basis'],notes=item['notes'],
                   faculty=item['faculty'],unit=item['unit'],student_type=item['student_type'],page_type=item['page_type'],
                   entry_year=str(item['entry_year']),entry_term=item['entry_term'],admission_pathway=item.get('admission_pathway',''),
                   knowledge_domain='student_services' if item['source_type']=='student_service' else 'academic_information')
        return row
    if selected['file_path'].startswith('files/extended_resources/'):
        manifest=json.loads((PROJECT/'files/extended_resources/download_manifest.json').read_text(encoding='utf-8'))
        item=next(r for r in manifest if r.get('file_path')==selected['file_path'])
        row.update(source_id='polyu_extended_'+hashlib.sha256(item['source_url'].encode()).hexdigest()[:16],
                   title=item['title'],source_url=item['source_url'],source_url_basis='public official link; download manifest records discovery and validation',
                   publisher='The Hong Kong Polytechnic University',source_type=item['source_type'],academic_year=item['academic_year'],
                   captured_at=item['captured_at'],year_basis=item['year_basis'],notes=item['notes'],
                   programme=item['programme_code'],faculty=item['faculty'],unit=item['unit'],student_type=item['student_type'],
                   knowledge_domain='student_services' if item['source_type']=='student_service' else 'academic_information',
                   page_type={'programme_requirements':'ProgrammeRequirements','subject_description':'SubjectDescription',
                              'programme_guidance':'ProgrammeGuidance','student_service':'StudentService'}[item['source_type']])
        # The year labels identify document versions. Cohort and entry year stay
        # unspecified until the actual applicability clause has been checked.
        return row
    if selected['file_path'].startswith('files/year_specific/'):
        manifest=json.loads((PROJECT/'files/year_specific/download_manifest.json').read_text(encoding='utf-8'))
        item=next(r for r in manifest if r.get('file_path')==selected['file_path'])
        key=item['source_url']+'|'+selected['file_path'] if item['source_type']=='programme_catalogue' else item['source_url']
        row.update(source_id='polyu_year_'+hashlib.sha256(key.encode()).hexdigest()[:16],
                   title=item['title'],source_url=item['source_url'],source_url_basis='official year-labelled page, visible entry/handbook year verified',
                   source_type=item['source_type'],academic_year=item['academic_year'],captured_at=item['captured_at'],
                   year_basis=item['year_basis'],notes=item['notes'])
        if item['source_type'] in {'programme_information','programme_catalogue'}:
            row.update(knowledge_domain='academic_information',programme=item.get('programme_code','not_programme_specific'),cohort=item['academic_year'],
                       faculty=item.get('faculty',''),unit=item.get('faculty',''),page_type='ProgrammeDetails',
                       entry_year=str(item['entry_year']),entry_term=item['entry_term'],student_type='taught_postgraduate')
            if item['source_type']=='programme_catalogue':
                row.update(page_type='Programmes',source_url_basis='locally assembled from verified official entry-labelled programme pages')
        else:
            row.update(knowledge_domain='policy',student_type='taught_programmes_mixed')
        return row
    if selected['file_path'].startswith('files/faculty wise rules/'):
        manifest = json.loads((PROJECT / 'files/faculty wise rules/download_manifest.json').read_text(encoding='utf-8'))
        item = next((r for r in manifest if r.get('file_path') == selected['file_path']), None)
        row.update(knowledge_domain='academic_information', source_type='academic_unit_information', student_type='mixed')
        if item:
            row.update(
                source_id='polyu_academic_' + hashlib.sha256(item['source_url'].encode()).hexdigest()[:16],
                title=item['title'], source_url=item['source_url'], source_url_basis='official directory discovery and download manifest',
                publisher='The Hong Kong Polytechnic University - ' + item['unit'],
                faculty=item['faculty'], unit=item['unit'], page_type=item['page_type'], captured_at=item['captured_at'],
                notes='Public academic-unit information, not an academic regulation. Snapshot may contain prospective intake details; do not infer admission cohort applicability. ' + item['notes'],
            )
        else:
            raw = content.decode('utf-8-sig',errors='replace')
            origin = re.search(r'saved from url=\(\d+\)(https?://\S+)',raw)
            if not origin:
                raise ValueError('Official directory origin missing')
            row.update(source_id='polyu_academic_unit_directory',title='PolyU Faculties, Schools and College',
                       source_url=html.unescape(origin.group(1)), source_url_basis='saved HTML origin comment',
                       page_type='Directory', notes='Official academic-unit directory; source capture date unconfirmed. Organisational information, not programme-specific academic regulations.')
        return row
    if path.suffix.lower() == '.html':
        raw = content.decode('utf-8-sig', errors='replace')
        match = re.search(r'saved from url=\(\d+\)(https?://\S+)', raw)
        if match:
            row['source_url'] = html.unescape(match.group(1))
            row['source_url_basis'] = 'saved HTML origin comment'
        match = re.search(r'<title[^>]*>(.*?)</title>', raw, re.I | re.S)
        row['title'] = html.unescape(re.sub(r'\s+', ' ', match.group(1)).strip()) if match else path.stem
        faq = re.match(r'Q(\d+)_', path.name)
        if faq:
            number = int(faq.group(1))
            row.update(source_id=f'polyu_registration_faq_q{number}', source_type='faq')
            # These articles explicitly discuss undergraduate curriculum/language/SL rules.
            if number in {17, 21, 22, 23, 26, 27, 28}:
                row['student_type'] = 'undergraduate'
                notes.append('Retain narrower eligibility conditions from the article; this label does not establish eligibility.')
            if number in {17, 26, 28}:
                row['student_type'] = 'full_time_undergraduate'
            if number == 23:
                row['cohort'] = '2018/19 to 2025/26'
                notes.append('Do not apply this cohort-specific language guidance to later cohorts without further evidence.')
            notes.append('Extract the main question and answer only; exclude related/recent article lists.')
        elif path.name.startswith('Preparation'):
            row.update(source_id='polyu_registration_preparation', source_type='procedure', student_type='mixed')
            notes.append('Contains both general guidance and student-group-specific clauses; label applicability at passage level.')
        elif path.name.startswith('Schedules'):
            row.update(source_id='polyu_registration_schedule_2026_27', source_type='schedule', academic_year='2026/27', student_type='mixed')
            notes.append('Dated snapshot: Semester One dates present; Semester Two says release in early December 2026; Summer Term pending. Do not infer missing dates.')
    elif path.name == 'Student_Handbook_2026-27_English.pdf':
        row.update(
            source_id='polyu_student_handbook_2026_27',
            title='Student Handbook for Taught Programmes 2026/27',
            source_url='https://www.polyu.edu.hk/ar/docdrive/polyu-students/student-handbook/Student_Handbook_2026-27_English.pdf',
            source_url_basis='official handbook download link checked in this review',
            source_type='handbook', academic_year='2026/27', student_type='taught_programmes_mixed',
        )
        notes.append('Published July 2026; retain cohort and programme exceptions at passage level.')
        row['year_basis']='explicit_handbook_academic_year'
    elif path.parent.name == 'registration guide':
        number = path.name[:2]
        if number not in GUIDE_TITLES:
            raise ValueError(f'Unrecognized guide: {path.name}')
        row.update(
            source_id=f'polyu_registration_guide_{number}', title=GUIDE_TITLES[number],
            source_url=GUIDE_BASE + path.name,
            source_url_basis=f'official guide page links verified 2026-11-19: {GUIDE_PAGE}',
            source_type='procedure',
        )
        notes.append('No policy academic year assigned from screenshot/example dates. URL mapping does not establish remote/local byte identity.')
        if number == '09':
            row['student_type'] = 'undergraduate'
        elif number == '04':
            row['student_type'] = 'mixed'
            notes.append('Final outside-curriculum procedure is restricted to full-time undergraduate students.')
    if not row['source_id']:
        raise ValueError(f'Unclassified source: {path}')
    row['notes'] = ' '.join(notes)
    return row


def main():
    rows = [make_record(item) for item in read_csv(DATA / 'sources_to_process.csv')]
    overrides_path = DATA / 'source_metadata_overrides.csv'
    overrides = read_csv(overrides_path) if overrides_path.exists() else []
    by_id = {item['source_id']: item for item in overrides}
    if len(by_id) != len(overrides):
        raise ValueError('Duplicate source IDs in metadata overrides')
    for row in rows:
        override = by_id.get(row['source_id'], {})
        for field in OVERRIDE_FIELDS[1:]:
            value = override.get(field, '').strip()
            if value:
                row[field] = row[field] + ' ' + value if field == 'notes' else value
        if row['captured_at']:
            datetime.fromisoformat(row['captured_at'])
        host = urlparse(row['source_url']).hostname or ''
        if host != 'polyu.edu.hk' and not host.endswith('.polyu.edu.hk'):
            raise ValueError(f'Missing/non-PolyU origin: {row["file_path"]}')
        row['metadata_status'] = 'catalogued' if row['captured_at'] else 'capture_date_unconfirmed'
    ids = [row['source_id'] for row in rows]
    assert len(ids) == len(set(ids)), 'Duplicate source IDs'
    # Several derived faculty/year catalogues can cite the same official index.
    primary_urls=[row['source_url'] for row in rows if row['source_type']!='programme_catalogue']
    assert len(set(primary_urls))==len(primary_urls), 'Duplicate primary source URLs'
    write_csv(DATA / 'sources.csv', FIELDS, rows)
    # Preserve user edits, and add blank entries for newly selected documents.
    for row in rows:
        if row['source_id'] not in by_id:
            overrides.append({field: row['source_id'] if field == 'source_id' else '' for field in OVERRIDE_FIELDS})
    write_csv(overrides_path, OVERRIDE_FIELDS, overrides)
    pending = sum(not row['captured_at'] for row in rows)
    report = (
        '# Source catalogue review\n\n'
        f'- Selected sources: {len(rows)}\n'
        f'- Official source URLs recorded: {sum(bool(r["source_url"]) for r in rows)}\n'
        f'- Unique IDs and primary-source URLs: validated (derived faculty catalogues can share the official index URL)\n'
        f'- Unconfirmed download/capture dates: {pending}\n\n'
        'Capture dates are intentionally blank when unconfirmed. File modification times are recorded separately and are not proof of download date.\n\n'
        'To supply known dates, edit captured_at in source_metadata_overrides.csv using YYYY-MM-DD, then rerun the script. Leave unknown dates blank. Do not replace them with the catalogue creation date.\n\n'
        'Academic year not_specified means the source was not explicitly dated; it does not mean the rule is current for every year. Student type not_specified means applicability must be checked in the text. Mixed sources require passage-level eligibility labels during extraction.\n\n'
        'Selected public 2026/27 PRDs and undated subject forms are included. This is partial programme coverage; verify cohort conditions inside each PRD.\n'
    )
    (DATA / 'source_catalogue_review.md').write_text(report, encoding='utf-8')
    print(f'Created data/sources.csv: {len(rows)} sources, all with official URLs and unique IDs.')
    print(f'Capture dates unconfirmed: {pending}. See data/source_catalogue_review.md.')
    print('Original downloads unchanged. No external Python packages required.')


if __name__ == '__main__':
    main()
