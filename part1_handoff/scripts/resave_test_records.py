"""Preserve original terminal saves, then rerun their questions into UTF-8 JSON."""
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from policy_rag.retrieve import PolicyRetriever


def main():
    files = sorted((ROOT / 'data').glob('test_q*.json'), key=lambda p:int(p.stem[6:]))
    questions = []
    for p in files:
        raw = p.read_text(encoding='utf-8-sig')
        match = re.search(r'"query"\s*:\s*("(?:[^"\\]|\\.)*")', raw)
        if not match:
            raise ValueError(f'Cannot safely recover question from {p.name}')
        questions.append((p, json.loads(match.group(1))))
    backup = ROOT / 'output' / 'original_test_records'
    backup.mkdir(parents=True,exist_ok=True)
    for p,_ in questions:
        if not (backup / p.name).exists():
            shutil.copy2(p, backup / p.name)
    # The user has already downloaded the model. This repair uses its local cache.
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    retriever = PolicyRetriever()
    for p,query in questions:
        result = retriever.search(query, method='semantic', top_k=5)
        result['record_note'] = 'Regenerated from the original saved question to avoid PowerShell encoding conversion; originals retained in output/original_test_records.'
        p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
        print(f'Saved {p.name}: {len(result["results"])} results', flush=True)
    print('All records regenerated. Original files were backed up.')


if __name__ == '__main__':
    main()
