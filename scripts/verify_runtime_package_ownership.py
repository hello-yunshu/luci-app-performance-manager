#!/usr/bin/env python3
"""Check Full/split/Stable/Preview ownership using real SDK APKs and dependencies.

All roots and an unsigned local repository are isolated below --output. Package
scripts are disabled; signature, daemon, UI, and device gates remain separate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from verify_apks import apk_file_content


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(args):
    if not __debug__:raise RuntimeError('ownership verification requires assertions')
    tool=args.apk.resolve();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    feed=output/'feed';feed.mkdir()
    products={key:getattr(args,key).resolve() for key in ['full','stable','preview','core','luci','glue']}
    expected={'full':'luci-app-performance-manager-all','stable':'rill-runtime','preview':'rill-runtime-preview',
              'core':'performance-manager','luci':'luci-app-performance-manager','glue':'performance-manager-rill'}
    metadata={};packages={};sources={}
    def add(path):
        info=json.loads(subprocess.check_output([str(tool),'--allow-untrusted','adbdump','--format','json',str(path)],text=True))['info']
        name=info['name'];version=info['version'];filename=name+'-'+version+'.apk'
        if not re.fullmatch(r'[A-Za-z0-9+_.~-]+\.apk',filename):raise ValueError('unsafe APK repository filename')
        if name in sources and sources[name]['version']!=version:
            raise ValueError('multiple SDK package versions would make dependency evidence ambiguous: '+name)
        target=feed/filename
        if target.exists():
            if digest(target)!=digest(path):raise ValueError('different APK bytes share a repository identity: '+filename)
        else:shutil.copyfile(path,target)
        sources[name]={'version':version,'sha256':digest(path),'file':filename}
        return info,target
    for path in sorted(args.sdk.resolve().joinpath('bin').rglob('*.apk')):add(path)
    for role,path in products.items():
        info,staged=add(path);assert info['name']==expected[role],(role,info)
        metadata[role]=info;packages[role]=staged
    arch=metadata['full']['arch']
    assert metadata['stable']['arch']==arch and metadata['preview']['arch']==arch
    binary=apk_file_content(products['stable'],'/usr/bin/rill-runtime')
    assert binary and hashlib.sha256(binary).hexdigest()==args.runtime_sha256
    assert apk_file_content(products['full'],'/usr/bin/rill-runtime')==binary
    required={'!'+name+'>=0' for name in [expected[r] for r in ['stable','preview','core','luci','glue']]}
    assert required<=set(metadata['full'].get('depends',[]))
    index=feed/'packages.adb'
    subprocess.run([str(tool),'mkndx','--allow-untrusted','--output',str(index),*map(str,sorted(feed.glob('*.apk')))],check=True,capture_output=True)
    rows=[]
    combinations=[('full',['full']),('stable',['stable']),('preview',['preview']),('split',['core','luci','glue','stable'])]
    pairs=[('full','stable'),('stable','full'),('full','preview'),('preview','full'),('full','split'),('split','full')]
    roles=dict(combinations)
    for first,second in pairs:
        root=output/(first+'-then-'+second);(root/'etc/apk/keys').mkdir(parents=True)
        (root/'repositories').write_text('file://'+str(index)+'\n')
        state=root/'etc/performance-manager/rill/ownership-state';state.parent.mkdir(parents=True)
        state.write_bytes(b'preserve independent user state\n')
        mode=[] if os.geteuid()==0 else ['--usermode']
        base=[str(tool),*mode,'--root',str(root),'--arch',arch,'--allow-untrusted','--no-network','--cache=no',
              '--keys-dir',str(root/'etc/apk/keys'),'--repositories-file',str(root/'repositories')]
        def run(command,*values,reject=False):
            flags=['--no-scripts'] if command in ['add','del','fix','upgrade'] else []
            p=subprocess.run([*base,*flags,command,*map(str,values)],capture_output=True,text=True,timeout=120)
            with (root/'commands.jsonl').open('a') as stream:
                stream.write(json.dumps({'command':command,'args':list(map(str,values)),'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})+'\n')
            if reject:assert p.returncode!=0,'incompatible composition accepted'
            else:assert p.returncode==0,p.stdout+p.stderr
            return p.stdout
        run('add','--initdb',*[packages[r] for r in roles[first]])
        installed=sorted(run('info').splitlines());world=(root/'etc/apk/world').read_bytes()
        protected={}
        for path in ['usr/bin/rill-runtime','usr/sbin/performance-manager.uc','etc/config/performance-manager']:
            file=root/path
            if file.is_file():protected[path]=digest(file)
        assert protected.get('usr/bin/rill-runtime')
        run('add',*[packages[r] for r in roles[second]],reject=True)
        assert sorted(run('info').splitlines())==installed,'rejected composition changed installed packages'
        assert (root/'etc/apk/world').read_bytes()==world,'rejected composition changed world'
        for path,sha in protected.items():assert digest(root/path)==sha,path
        assert state.read_bytes()==b'preserve independent user state\n'
        run('del',*[expected[r] for r in roles[first]])
        assert not (root/'usr/bin/rill-runtime').exists()
        assert state.read_bytes()==b'preserve independent user state\n'
        run('add',*[packages[r] for r in roles[first]])
        assert state.read_bytes()==b'preserve independent user state\n'
        assert digest(root/'usr/bin/rill-runtime')==protected['usr/bin/rill-runtime']
        rows.append({'first':first,'rejected':second,'installedAndWorldUnchanged':True,'protectedPayloadSha256':protected,
                     'removeReinstallPreservedState':True,'installedPackages':{name:sources[name] for name in installed if name in sources}})
    result={'scope':'real SDK APK Full/split/runtime ownership','releaseEligible':False,'packageScripts':'NOT RUN',
            'deviceQualification':False,'dependencyClosure':'real SDK packages resolved by apk; no fake providers',
            'runtimeBinarySha256':args.runtime_sha256,'products':{role:metadata[role] for role in products},'cases':rows}
    (output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['apk','sdk','full','stable','preview','core','luci','glue','output']:parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--runtime-sha256',required=True)
    args=parser.parse_args();print(json.dumps(verify(args),indent=2))


if __name__=='__main__':main()
