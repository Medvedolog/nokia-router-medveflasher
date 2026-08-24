#!/usr/bin/env python3
from pathlib import Path
import argparse, hashlib, json, shutil

def sha(p):
    h=hashlib.sha256();
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('openwrt_tree', type=Path); ns=ap.parse_args()
    root=ns.openwrt_tree.resolve(); here=Path(__file__).resolve().parent
    linux=[root/'target/linux/generic/backport-6.18/436-v7.3-mtd-spinand-fmsh-add-support-for-FM25G01B-FM25G02B.patch',root/'target/linux/generic/backport-6.18/437-v7.3-mtd-spinand-fmsh-fix-FM25G01B-FM25G02B-Quad-IO-read-dummy-cycles.patch']
    for p in linux:
        if not p.is_file(): raise SystemExit(f'ERROR: Linux Fudan patch missing: {p}')
    dst=root/'package/boot/uboot-airoha/patches/100-mtd-spinand-fmsh-add-fm25g0102b.patch'
    src=here/'100-mtd-spinand-fmsh-add-fm25g0102b.patch'
    if dst.exists() and sha(dst)!=sha(src): raise SystemExit(f'ERROR: conflicting U-Boot patch already exists: {dst}')
    shutil.copy2(src,dst)
    print('OK Linux Fudan patches present')
    print('OK installed U-Boot Fudan patch:', dst)
    print('PATCH_SHA256', sha(dst))
    print('NEXT: build an7581 Nokia MD UBI images; do not release until produced bytes are imported and pinned.')
if __name__=='__main__': main()
