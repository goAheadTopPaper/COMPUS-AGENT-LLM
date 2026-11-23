"""Repair generated metadata after moving Regulation to files/School Regulation.

Does not move source files or change passage text, IDs, rankings or embeddings.
Validates each destination against the existing catalogue checksum first.
"""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
OLD = 'Regulation/'
NEW = 'files/School Regulation/'


def new_path(value):
    return NEW + value[len(OLD):] if value.startswith(OLD) else value


def main():
    catalogue = ROOT / 'data/sources.csv'
    with catalogue.open(encoding='utf-8-sig',newline='') as stream:
        sources = list(csv.DictReader(stream))
    for row in sources:
        target = ROOT / new_path(row['file_path'])
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError(f'Missing or changed source: {target}')
    backups = ROOT / 'output/source_paths_before_reorganisation'
    backups.mkdir(parents=True,exist_ok=True)
    for name in ['sources.csv','sources_to_process.csv','excluded_files.csv']:
        path = ROOT / 'data' / name
        if not (backups / name).exists():
            shutil.copy2(path,backups / name)
        with path.open(encoding='utf-8-sig',newline='') as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames
            rows = list(reader)
        for row in rows:
            row['file_path'] = new_path(row['file_path'])
        with path.open('w',encoding='utf-8-sig',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    for name in ['documents.jsonl','chunks.jsonl']:
        path = ROOT / 'data' / name
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        for row in rows:
            row['file_path'] = new_path(row['file_path'])
        path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
    with sqlite3.connect(ROOT / 'data/policy_index.sqlite') as conn:
        records = list(conn.execute('SELECT id,payload FROM passages'))
        for key,payload in records:
            row = json.loads(payload)
            row['file_path'] = new_path(row['file_path'])
            conn.execute('UPDATE passages SET payload=? WHERE id=?',(json.dumps(row,ensure_ascii=False),key))
    print(f'Validated {len(sources)} relocated sources and updated metadata paths.')
    print('Passage IDs, text and existing semantic vectors unchanged.')


if __name__ == '__main__':
    main()
