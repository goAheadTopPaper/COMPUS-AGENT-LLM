"""Run existing Part 1 checks offline and keep their exit status/logs."""
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
env=dict(os.environ,HF_HUB_OFFLINE='1')
names=sys.argv[1:]
results=[]
for name in names:
 if not name.startswith('check_') or not name.replace('_','').isalnum():raise ValueError(name)
 p=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts'/f'{name}.py')],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
 results.append(dict(suite=name,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
 print(name, 'PASS' if p.returncode==0 else 'FAIL',p.stdout[-900:],flush=True)
 if p.returncode:print(p.stderr[-2000:],flush=True)
(ROOT/'data'/f'part1_regression_{names[0]}.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(int(any(x['exit_code'] for x in results)))
