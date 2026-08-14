#!/usr/bin/env python3
"""Convert top-level `function name(...) { }` declarations in
performance-manager.uc to `let name;` hoisted declarations + `name = (...) => {}`
assignments. ucode resolves free-variable bindings at function-definition time
and does NOT hoist function declarations, so any forward reference crashes at
runtime. `let` bindings, by contrast, are scope-wide, so a function defined
earlier can safely call a function assigned later as long as the call happens
after all assignments (which is the case here: all calls are at the bottom).

Usage: python3 convert_hoist.py INPUT [OUTPUT]
If OUTPUT is omitted, prints the transformed source to stdout and the diff summary.
"""
import re
import sys

path = sys.argv[1]
out_path = sys.argv[2] if len(sys.argv) > 2 else None

src = open(path).read()
lines = src.split('\n')

DECL = re.compile(r'^function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{?\s*$')
DECL1 = re.compile(r'^function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{\s*(.+)\}\s*$')

decl_lines = {}   # lineno(1-based) -> name
sig_map = {}      # name -> params string
oneline = {}      # lineno -> body string
for i, ln in enumerate(lines, 1):
    m = DECL.match(ln)
    m1 = DECL1.match(ln)
    if m and not m1:
        name, params = m.group(1), m.group(2)
        decl_lines[i] = name
        sig_map[name] = params
        if not ln.rstrip().endswith('{'):
            raise SystemExit(f'decl at L{i} does not end with {{ on same line: {ln!r}')
    elif m1:
        name, params, body = m1.group(1), m1.group(2), m1.group(3)
        decl_lines[i] = name
        sig_map[name] = params
        oneline[i] = body

if not decl_lines:
    raise SystemExit('no top-level function declarations found')

first_decl = min(decl_lines)
last_decl = max(decl_lines)

# Sanity: every line from first to last decl at column 0 is either a decl or a
# closing '}' or a comment. (This verifies no interleaved executable statements.)
for i in range(first_decl, last_decl + 1):
    if i in decl_lines:
        continue
    ln = lines[i - 1]
    if ln and ln[0] in ' \t':
        continue  # indented -> inside a function body
    if re.match(r'^}\s*$', ln):
        continue
    if not ln.strip() or ln.strip().startswith('//'):
        continue
    raise SystemExit(f'unexpected col-0 line at L{i}: {ln!r}')

# Build hoisted let block
hoist_lines = [
    '/* ucode resolves free variables when a function is DEFINED and does not',
    ' * hoist function declarations, so forward references would crash at',
    ' * runtime. Declare every top-level function name here so the assignments',
    ' * below can resolve regardless of definition order. */',
    'let ' + ',\n\t'.join(decl_lines.values()) + ';',
    '',
]

new_lines = []
open_arrow = False
for i, ln in enumerate(lines, 1):
    if i == first_decl:
        new_lines.extend(hoist_lines)
    if i in decl_lines:
        name = decl_lines[i]
        params = sig_map[name]
        if i in oneline:
            # single-line decls are converted inline; terminate the statement
            new_lines.append(f'{name} = ({params}) => {{ {oneline[i]} }};')
        else:
            new_lines.append(f'{name} = ({params}) => {{')
            open_arrow = True
    elif open_arrow and re.match(r'^}\s*$', ln):
        # ucode does not apply ASI after a block-bodied arrow assignment, so an
        # explicit ';' is required to terminate the expression statement.
        new_lines.append('};')
        open_arrow = False
    else:
        new_lines.append(ln)

result = '\n'.join(new_lines)

# Verify no forward references remain
def find_forward(text):
    flines = text.split('\n')
    dlines = {}
    for idx, ln in enumerate(flines, 1):
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\(([^)]*)\)\s*=>\s*\{', ln)
        if m:
            dlines[m.group(1)] = idx
    KW = set('function if for while switch case return break continue else in of delete typeof new throw try catch do let const import export as'.split())
    names = sorted(dlines, key=dlines.get)
    fwd = {}
    for i, name in enumerate(names):
        start = dlines[name]
        end = dlines[names[i + 1]] if i + 1 < len(names) else len(flines) + 1
        body = '\n'.join(flines[start:end])
        for m in re.finditer(r'(?<![\w.$])([A-Za-z_][A-Za-z0-9_]*)\s*\(', body):
            cal = m.group(1)
            if cal in KW:
                continue
            if cal in dlines and dlines[cal] > start:
                fwd.setdefault((start, name), []).append((cal, dlines[cal]))
    return fwd

fwd = find_forward(result)
print(f'functions: {len(decl_lines)}  hoisted-decls: {len(hoist_lines)-2}')
if fwd:
    # These are benign: every callee is a hoisted `let` binding declared at the
    # top, so the call resolves as long as it happens after assignment (it does —
    # all calls are at the bottom, after the assignment sequence).
    unresolved = []
    for (ln, name), cals in fwd.items():
        for c, cl in cals:
            if c not in set(decl_lines.values()):
                unresolved.append((ln, name, c, cl))
    if unresolved:
        print(f'FATAL: callees not covered by hoist block: {unresolved}')
        raise SystemExit(1)
    print(f'forward refs resolved by hoisting: {sum(len(c) for c in fwd.values())}')
else:
    print('no forward references remain')

if out_path:
    with open(out_path, 'w') as f:
        f.write(result)
    print(f'wrote {out_path}')
else:
    sys.stdout.write(result)
