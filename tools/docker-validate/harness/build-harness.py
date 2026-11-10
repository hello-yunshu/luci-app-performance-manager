#!/usr/bin/env python3
"""Build the REAL Core ucode runtime harness artefact.

The runtime harness executes the ACTUAL package/performance-manager/files/
usr/sbin/performance-manager.uc, so behavior is verified against the real Core
logic, not a Python mirror.

The shipped Core is written callee-before-caller (ucode resolves free-variable
bindings at function-DEFINITION time and does not hoist function declarations,
so the production source is kept forward-reference-free — no transform needed).
The daemon's ambient `let conn = ubusmod.connect()` is neutralised and the
main-entry block is stripped so the file loads as a library; the test driver
then re-seats the data-provider seams (run, read, command_exists,
interface_dump, device_dump, netdevs, stable_target, integration_state, etc.)
to fixtures and asserts on the real Core's output.  NO semantic transform is
applied: `convert_hoist.py` was removed (CORE BLOCKER C).

Usage: python3 build-harness.py [OUT.uc] [DRIVER.frag]
The test driver is read from core_runtime_test.uc.frag (appended verbatim).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / 'package/performance-manager/files/usr/sbin/performance-manager.uc'
DEFAULT_DRIVER = Path(__file__).resolve().parent / 'core_runtime_test.uc.frag'
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / 'build/core_runtime_test.uc'
DRIVER = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DRIVER

# 1. Read the shipped Core verbatim (already forward-reference-free; NO hoist).
raw = CORE.read_text()

# 2. Strip the daemon main-entry block: it starts at the first top-level exec
#    statement after the function bodies (ensure_dir(...) / uloop.init /
#    conn.publish / uloop.run). Everything from that marker to EOF is the
#    service entry, not library logic.
lines = raw.split('\n')
main_start = None
for i, ln in enumerate(lines):
    if ln.startswith('ensure_dir(') or ln.startswith('uloop.init()'):
        main_start = i
        break
if main_start is None:
    raise SystemExit('could not locate daemon main-entry marker in Core')
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
