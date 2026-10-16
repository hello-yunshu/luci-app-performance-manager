#!/usr/bin/env python3
"""Download the same-qualified Preview only as an ownership-conflict fixture.

The supported PM contract remains Stable. This derives a temporary selector
from that contract's exact, digest-bound dual-channel qualification manifest.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


def fixture_contract(contract,raw):
    if hashlib.sha256(raw).hexdigest()!=contract['qualification'].get('manifestSha256'):
        raise ValueError('companion manifest differs from supported Stable qualification')
    data=json.loads(raw)
    if data.get('schemaVersion')!=3 or data.get('releaseEligible') is not True:
        raise ValueError('companion fixture requires complete hosted schema 3 qualification')
    for key,expected in [('packageCommit',contract['openwrtPackage']['commit']),
                         ('runId',contract['qualification']['runId']),
                         ('runAttempt',contract['qualification'].get('runAttempt'))]:
        if data.get(key)!=expected:raise ValueError('companion fixture qualification identity mismatch: '+key)
    current=contract['openwrtPackage']
    for key,field in [('name','package'),('version','packageVersion'),('release','packageRelease')]:
        if data['package'][key]!=current[field]:raise ValueError('manifest does not contain the supported Stable package')
    peer=data['previewPackage']
    if peer.get('qualificationState')!='PASS' or peer['name']!='rill-runtime-preview':
        raise ValueError('companion Preview is not qualified')
    result=copy.deepcopy(contract)
    result['openwrtPackage'].update(package=peer['name'],packageVersion=peer['version'],packageRelease=peer['release'])
    result['preview']={**result.get('preview',{}),'commit':peer['upstream']['commit']}
    result['testOnlyPurpose']='same-run Preview ownership conflict fixture; not supported PM Runtime'
    return result


def main():
    sys.dont_write_bytecode=True
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['contract','qualified-manifest','package-dir','output']:parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--openwrt-version',required=True)
    parser.add_argument('--architecture',required=True)
    parser.add_argument('--apk',required=True)
    args=parser.parse_args();contract=json.loads(args.contract.read_text())
    selector=fixture_contract(contract,args.qualified_manifest.read_bytes())
    head=subprocess.check_output(['git','-C',str(args.package_dir),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(args.package_dir),'status','--porcelain'],text=True).strip()
    if head!=contract['openwrtPackage']['commit'] or dirty:raise ValueError('fixture verifier checkout must be the exact clean pinned producer')
    path=args.package_dir/'scripts/qualified_runtime_artifacts.py'
    if not path.is_file():raise ValueError('canonical qualified artifact verifier is missing')
    sys.path.insert(0,str(path.parent.resolve()))
    spec=importlib.util.spec_from_file_location('canonical_qualified_fixture',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    package,target=module.fetch_qualified(selector,args.package_dir,args.openwrt_version,args.architecture,'apk',args.output,args.apk,channel='preview')
    print(json.dumps({'scope':'same-run conflict fixture only','supportedPMRuntime':False,'package':str(package),'qualifiedTarget':target},indent=2))


if __name__=='__main__':main()
