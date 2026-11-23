"""Create a portable handoff archive without caches or webpage resource folders."""
from pathlib import Path
import csv
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / 'output' / 'part1_handoff.zip'
    target.parent.mkdir(exist_ok=True)
    paths = [ROOT / 'PART1_GUIDE.md',ROOT / 'README.md', ROOT / 'requirements-part1.txt',ROOT / 'requirements-semantic.txt']
    if (ROOT/'START_HERE.md').is_file():
        paths.append(ROOT/'START_HERE.md')
    for folder in ['policy_rag', 'examples', 'scripts']:
        paths.extend((ROOT / folder).glob('*.py'))
    paths.extend(p for p in (ROOT / 'data').iterdir() if p.is_file())
    with (ROOT / 'data/sources.csv').open(encoding='utf-8-sig',newline='') as stream:
        paths.extend(ROOT / row['file_path'] for row in csv.DictReader(stream))
    for name in ['download_manifest.json','download_manifest.csv','COLLECTION_README.md']:
        paths.append(ROOT / 'files/faculty wise rules' / name)
    for name in ['download_manifest.json','TPg_Catalogue.html']:
        p=ROOT/'files/year_specific'/name
        if p.is_file():
            paths.append(p)
    paths.extend(p for p in (ROOT/'files/extended_resources').glob('*.json'))
    paths.extend(p for p in (ROOT/'files/extended_resources').glob('*.md'))
    # Audit snapshots are not indexed, but allow teammates to inspect currency comparisons.
    paths.extend(p for p in (ROOT/'files/currency_check').glob('*') if p.is_file())
    paths.extend(p for p in (ROOT/'files/schoolwide').glob('*.json'))
    paths.extend(p for p in (ROOT/'files/schoolwide').glob('*.md'))
    paths.extend(p for p in (ROOT/'files/schoolwide/indexes').glob('*.html'))
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            archive.write(path, path.relative_to(ROOT).as_posix())
    print(f'Created {target.name}: {len(set(paths))} files; {target.stat().st_size/1024/1024:.1f} MB')
    print('Contains selected originals for re-extraction; webpage assets and caches are excluded.')


if __name__ == '__main__':
    main()
