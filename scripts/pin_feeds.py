#!/usr/bin/env python3
"""Pin SDK feeds to the exact commits of the official OpenWrt release.

Runs from inside an extracted OpenWrt SDK directory. Reads feeds.buildinfo
(either shipped with the SDK or supplied via FEEDS_BUILDINFO_URL) and checks
out each pinned commit, verifying HEAD afterwards. Fails closed if any feed
cannot be pinned.
"""
from __future__ import annotations
import os, re, subprocess, sys, urllib.request
from pathlib import Path

commit_re = re.compile(r'^\^?[0-9a-f]{40}$')
pinned = {}
info = Path('feeds.buildinfo')
if not info.exists():
    url = os.environ.get('FEEDS_BUILDINFO_URL')
    if not url:
        sys.exit('feeds.buildinfo missing and FEEDS_BUILDINFO_URL not set')
    urllib.request.urlretrieve(url, info)
for line in info.read_text().splitlines():
    parts = line.split()
    if len(parts) == 3 and commit_re.match(parts[2]):
        pinned[parts[0]] = parts[2].lstrip('^')
if not pinned:
    sys.exit('no pinned feed commits found in feeds.buildinfo')
bad = []
for name, commit in pinned.items():
    repo = Path('feeds') / name
    if not repo.is_dir():
        continue
    r = subprocess.run(['git', '-C', str(repo), 'checkout', '-q', commit], capture_output=True, text=True)
    if r.returncode != 0:
        bad.append(f'{name}: checkout failed: {r.stderr.strip()}')
        continue
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    if head != commit:
        bad.append(f'{name}: HEAD {head} != pinned {commit}')
if bad:
    sys.exit('feed pin verification failed: ' + '; '.join(bad))
print('feeds pinned to official release commits:', ', '.join(sorted(pinned)))
