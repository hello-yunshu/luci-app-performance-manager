#!/usr/bin/env python3
"""Build the REAL Core ucode runtime harness artefact.

The runtime harness executes the ACTUAL package/performance-manager/files/
usr/sbin/performance-manager.uc (after the same ucode-hoist transform the
OpenWrt container gate uses), so behavior is verified against the real Core
logic, not a Python mirror.

This script:
  1. hoists the readable Core source (convert_hoist) into the runtime-correct
     form;
  2. strips the daemon main-entry block (ensure_dir/ubus publish/uloop.run) so
     the file loads as a library instead of starting the service;
  3. neutralises the ambient `ubusmod.connect()` (no ubus in the harness) so the
     library loads without exiting;
  4. appends a test driver that reassigns the data-provider seam (conn, run,
     read, command_exists, interface_dump, device_dump, netdevs, stable_target)
     to fixtures and asserts on the real Core's output.

Usage: python3 build-harness.py [OUT.uc]
The test driver is read from core_runtime_test.uc.frag (appended verbatim).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / 'package/performance-manager/files/usr/sbin/performance-manager.uc'
HOIST = ROOT / 'tools/docker-validate/convert_hoist.py'
DRIVER = Path(__file__).resolve().parent / 'core_runtime_test.uc.frag'
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / 'build/core_runtime_test.uc'

# 1. Produce the ucode-hoisted (runtime-correct) Core artifact.
import subprocess
hoisted = subprocess.run(
    [sys.executable, str(HOIST), str(CORE)],
    capture_output=True, text=True, check=True).stdout

# 2. Strip the daemon main-entry block: it starts at the first top-level exec
#    statement after the function assignments (ensure_dir(...) / uloop.init /
#    conn.publish / uloop.run). Everything from that marker to EOF is the
#    service entry, not library logic.
lines = hoisted.split('\n')
main_start = None
for i, ln in enumerate(lines):
    if ln.startswith('ensure_dir(') or ln.startswith('uloop.init()'):
        main_start = i
        break
if main_start is None:
    raise SystemExit('could not locate daemon main-entry marker in hoisted Core')
lib = '\n'.join(lines[:main_start])

# 3. Neutralise the ambient ubus connect + guard so the library loads without
#    a real ubus daemon (the test driver re-seats `conn` to its own fixture).
lib = lib.replace('let conn = ubusmod.connect();', 'let conn = null;')
lib = re.sub(
    r"if \(!conn\) \{\s*warn\('[^\n']*'\);\s*exit\(1\);\s*\}", '', lib)
lib = re.sub(r"if \(!conn\) \{\s*warn\([^\n]*\);\s*exit\(1\);\s*\}", '', lib)

if not DRIVER.exists():
    raise SystemExit(f'test driver fragment missing: {DRIVER}')

driver = DRIVER.read_text()
out = lib + '\n' + driver
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(out)
print(f'wrote harness artefact -> {OUT} ({len(out.splitlines())} lines)')