#!/usr/bin/env python3
"""Maintain the cached upstream SQLite database used for incremental D1 diffs."""
import argparse
import json
import os
from pathlib import Path
import sys

LIB = Path(__file__).resolve().parents[2] / 'addons/plugin.video.mirantir/resources/lib'
sys.path.insert(0, str(LIB))
import source

from export_catalogue import generation_for

parser = argparse.ArgumentParser()
parser.add_argument('--db', type=Path, required=True)
parser.add_argument('--state', type=Path, required=True)
parser.add_argument('--source-repo')
args = parser.parse_args()
if args.source_repo:
 os.environ['PALANTIR_DB_REPO'] = args.source_repo
args.db.parent.mkdir(parents=True, exist_ok=True)
info = source.discover(str(args.state))
source.sync(str(args.db), str(args.state), info=info)
print(json.dumps({
 'generation': generation_for(info), 'source': info['repo'],
 'snapshot': info['name'], 'patches': [p['name'] for p in info.get('patches', [])]
}, indent=2))
