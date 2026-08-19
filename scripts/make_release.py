#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, os, subprocess, time, zipfile
ROOT=Path(__file__).resolve().parents[1]
version=(ROOT/'VERSION').read_text().strip(); dist=ROOT/'dist'; dist.mkdir(exist_ok=True)
out=dist/f'openwrt-performance-manager-{version}.zip'
# ZIP timestamps cannot be earlier than 1980. SOURCE_DATE_EPOCH makes repeat packaging byte-stable.
epoch=int(os.environ.get('SOURCE_DATE_EPOCH','1786579200'))  # 2026-08-13 00:00:00 UTC
stamp=time.gmtime(max(epoch,315532800))[:6]
manifest=[]
tracked = subprocess.run(
    ['git', '-C', str(ROOT), 'ls-files', '-z'], check=True,
    stdout=subprocess.PIPE,
).stdout.decode().split('\0')
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for rel_text in sorted(x for x in tracked if x):
        rel=Path(rel_text); p=ROOT/rel
        if not p.is_file():
            raise SystemExit(f'tracked source file missing: {rel}')
        data=p.read_bytes()
        manifest.append({'path':str(rel),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        zi=zipfile.ZipInfo(str(Path(f'openwrt-performance-manager-{version}')/rel), stamp)
        zi.compress_type=zipfile.ZIP_DEFLATED
        zi.external_attr=((p.stat().st_mode & 0o777) << 16)
        z.writestr(zi,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
manifest_path=dist/f'openwrt-performance-manager-{version}.manifest.json'
manifest_path.write_text(json.dumps({'version':version,'files':manifest},indent=2)+'\n')
h=hashlib.sha256(out.read_bytes()).hexdigest(); (dist/f'{out.name}.sha256').write_text(f'{h}  {out.name}\n')
print(out); print(h); print(manifest_path)
