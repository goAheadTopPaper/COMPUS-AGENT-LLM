"""One-command rebuild, using only already-downloaded local files/models."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model',default='sentence-transformers/all-MiniLM-L6-v2')
    parser.add_argument('--online',action='store_true',help='Allow model downloads if it is not cached')
    args = parser.parse_args()
    for package in ['pypdf','lxml','sentence_transformers']:
        try:
            __import__(package)
        except ImportError:
            raise SystemExit('Install dependencies first: python -m pip install -r requirements-semantic.txt')
    env = os.environ.copy()
    if not args.online:
        env['HF_HUB_OFFLINE'] = '1'
    commands = [
        ['scripts/build_year_catalogues.py'],
        ['scripts/prepare_source_list.py'],['scripts/build_source_catalogue.py'],
        ['-m','policy_rag.prepare'],['-m','policy_rag.retrieve','--build','--model',args.model],
        ['scripts/write_schoolwide_coverage.py'],['scripts/check_schoolwide.py'],['scripts/check_service_eligibility.py'],['scripts/check_verifier.py'],
        ['scripts/check_part1.py'],['scripts/check_faculty_integration.py'],['scripts/check_year_retrieval.py'],['scripts/check_policy_ranking.py'],['scripts/check_extended_resources.py'],['scripts/check_part1_acceptance.py'],['scripts/write_year_coverage.py'],['scripts/write_extended_coverage.py'],['scripts/package_part1.py'],
    ]
    for command in commands:
        print('Running: python ' + ' '.join(command),flush=True)
        subprocess.run([sys.executable,'-X','utf8',*command],cwd=ROOT,env=env,check=True)


if __name__ == '__main__':
    main()
