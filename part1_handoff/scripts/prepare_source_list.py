"""List source documents for processing without changing the downloads.

Run from any directory: python path/to/scripts/prepare_source_list.py
"""
from pathlib import Path
import csv
import json

PROJECT = Path(__file__).resolve().parents[1]
RAW = PROJECT / 'files' / 'School Regulation'
# Support handoff copies made before the source-folder reorganisation.
if not RAW.is_dir():
    RAW = PROJECT / 'Regulation'
DATA = PROJECT / 'data'
FACULTY = PROJECT / 'files/faculty wise rules'


def main():
    if not RAW.is_dir():
        raise SystemExit(f'Missing source folder: {RAW}')
    DATA.mkdir(exist_ok=True)
    included, excluded = [], []
    for path in sorted(RAW.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(PROJECT)
        extension = path.suffix.lower()
        if any(part.lower().endswith('_files') for part in path.relative_to(RAW).parts[:-1]):
            reason = 'Webpage resource; not a knowledge document'
        elif extension not in {'.pdf', '.html'}:
            reason = 'Not a PDF or HTML document'
        elif path.name == 'PolyUMSc_Brochure_2024-MT-250618.pdf':
            reason = 'Promotional brochure; exclude from authoritative rules'
        elif path.name in {
            'Subject Registration & Study Options _ Add Subjects FAQs.html',
            'Subject Registration & Study Options _ Drop Subjects FAQs.html',
        }:
            reason = 'FAQ index; individual answer articles are available'
        else:
            reason = ''
        row = {'file_path': relative.as_posix(), 'file_type': extension.lstrip('.'), 'reason': reason}
        (excluded if reason else included).append(row)

    manifest_path = FACULTY / 'download_manifest.json'
    if manifest_path.exists():
        for item in json.loads(manifest_path.read_text(encoding='utf-8')):
            if not item.get('file_path'):
                continue
            reason = '' if item['status'] == 'downloaded' else 'Insufficient extracted text; requires visual review before indexing'
            row = {'file_path':item['file_path'], 'file_type':'html', 'reason':reason}
            (excluded if reason else included).append(row)
        directory = list(FACULTY.glob('Faculties*.html'))
        if len(directory) == 1:
            included.append({'file_path':directory[0].relative_to(PROJECT).as_posix(),'file_type':'html','reason':''})
    year_manifest=PROJECT/'files/year_specific/download_manifest.json'
    if year_manifest.exists():
        for item in json.loads(year_manifest.read_text(encoding='utf-8')):
            if item['status']=='downloaded':
                included.append({'file_path':item['file_path'],'file_type':Path(item['file_path']).suffix.lstrip('.'),'reason':''})

    extended=PROJECT/'files/extended_resources/download_manifest.json'
    if extended.exists():
        for item in json.loads(extended.read_text(encoding='utf-8')):
            if item['status']=='downloaded':
                included.append({'file_path':item['file_path'],'file_type':item['file_type'],'reason':''})
    schoolwide=PROJECT/'files/schoolwide/download_manifest.json'
    if schoolwide.exists():
        for item in json.loads(schoolwide.read_text(encoding='utf-8')):
            if item['status']=='downloaded':
                included.append({'file_path':item['file_path'],'file_type':item['file_type'],'reason':''})

    for filename, rows in [('sources_to_process.csv', included), ('excluded_files.csv', excluded)]:
        with (DATA / filename).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['file_path', 'file_type', 'reason'])
            writer.writeheader()
            writer.writerows(rows)
    print(f'Included {len(included)} source documents.')
    print(f'Excluded {len(excluded)} resource/index/brochure files.')
    print('Original downloads were not modified.')


if __name__ == '__main__':
    main()
