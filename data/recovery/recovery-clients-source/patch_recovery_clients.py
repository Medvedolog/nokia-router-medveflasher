#!/usr/bin/env python3
"""Embed pinned AArch64 recovery transport clients into transient FIT initramfs.

RC19 transport policy:
- every MD/MF transition and stock-recovery initramfs contains the exact pinned
  nokia-tftp and nokia-scp AArch64 clients;
- /usr/bin/tftp -> nokia-tftp and /usr/bin/scp -> nokia-scp;
- Dropbear is started with -B because these transient images intentionally use
  an empty root password for the local recovery control-plane;
- production sysupgrade payloads are never modified.

The Linux Image is linked; bytes after the embedded newc archive must not move.
This patcher therefore rebuilds only the cpio archive inside its existing byte
window and leaves every byte outside that window untouched.  Stock-recovery
images reclaim a few APK *metadata-only* records to fit the two tiny clients;
no executable, config, LuCI asset, kernel module, firmware or restore tool is
removed.
"""
from __future__ import annotations
import argparse, hashlib, lzma, struct, sys
from dataclasses import dataclass
from pathlib import Path

HERE=Path(__file__).resolve().parent
NETSRC=HERE.parent/'transition-network-source'
sys.path.insert(0,str(NETSRC))
from patch_transition_network import Fdt, cstr, hash_image  # type: ignore

FDT_MAGIC=0xD00DFEED
DROPBEAR_OLD=b'procd_set_param command "$PROG" -F -P "$pid_file"'
DROPBEAR_NEW=b'procd_set_param command "$PROG" -F -B -P "$pid_file"'
RECLAIM=(
    'lib/apk/db/scripts.tar.gz',
    'lib/apk/packages/luci-base.list',
    'lib/apk/packages/busybox.list',
)

def a4(n:int)->int: return (n+3)&~3

@dataclass
class Entry:
    magic:bytes; vals:list[int]; name:str; data:bytes
    @property
    def mode(self): return self.vals[1]

def parse_archive_at(raw:bytes,start:int):
    p=start; out=[]
    try:
        while True:
            h=raw[p:p+110]
            if len(h)!=110 or h[:6] not in (b'070701',b'070702'): return None
            magic=h[:6]; vals=[int(h[6+i*8:14+i*8],16) for i in range(13)]; p+=110
            fs=vals[6]; ns=vals[11]
            if ns<1 or ns>4096 or p+ns>len(raw): return None
            nb=raw[p:p+ns]; p=a4(p+ns)
            if not nb.endswith(b'\0'): return None
            name=nb[:-1].decode('utf-8','surrogateescape')
            if p+fs>len(raw): return None
            data=raw[p:p+fs]; p=a4(p+fs)
            out.append(Entry(magic,vals,name,data))
            if name=='TRAILER!!!':
                if len(out)>100 and any(e.name=='bin/busybox' for e in out): return start,p,out
                return None
    except Exception:
        return None

def find_archive(raw:bytes):
    pos=0
    while True:
        s=raw.find(b'070701',pos)
        if s<0: raise ValueError('embedded newc initramfs not found')
        got=parse_archive_at(raw,s)
        if got: return got
        pos=s+1

def build_entry(e:Entry)->bytes:
    vals=e.vals[:]
    vals[6]=len(e.data); vals[11]=len(e.name.encode('utf-8','surrogateescape'))+1; vals[12]=0
    h=e.magic+b''.join(f'{v:08x}'.encode('ascii') for v in vals)
    assert len(h)==110
    nb=e.name.encode('utf-8','surrogateescape')+b'\0'
    out=bytearray(h); out+=nb; out+=b'\0'*((-len(out))%4); out+=e.data; out+=b'\0'*((-len(out))%4)
    return bytes(out)

def new_entry(name:str,data:bytes,mode:int,ino:int)->Entry:
    # ino, mode, uid, gid, nlink, mtime, filesize, devmajor, devminor,
    # rdevmajor, rdevminor, namesize, check
    vals=[ino,mode,0,0,1,0,len(data),0,0,0,0,len(name.encode())+1,0]
    return Entry(b'070701',vals,name,data)

def patch_cpio(raw:bytes,tftp:bytes,scp:bytes,recovery:bool):
    start,end,entries=find_archive(raw)
    next_nonzero=end
    while next_nonzero<len(raw) and raw[next_nonzero]==0: next_nonzero+=1
    capacity=next_nonzero-start
    names={e.name for e in entries}
    if 'etc/init.d/dropbear' not in names or 'etc/shadow' not in names: raise ValueError('required recovery auth files missing')
    shadow=next(e.data for e in entries if e.name=='etc/shadow')
    if not shadow.startswith(b'root:::'): raise ValueError('transient root account is not intentionally blank')
    maxino=max(e.vals[0] for e in entries)
    rebuilt=[]; removed=[]
    for e in entries:
        if e.name=='TRAILER!!!': continue
        if e.name in ('usr/bin/nokia-tftp','usr/bin/nokia-scp','usr/bin/tftp','usr/bin/scp'):
            continue
        if recovery and e.name in RECLAIM:
            removed.append((e.name,len(e.data))); continue
        if e.name=='etc/init.d/dropbear':
            if DROPBEAR_NEW not in e.data:
                if e.data.count(DROPBEAR_OLD)!=1: raise ValueError('unexpected Dropbear command layout')
                e=Entry(e.magic,e.vals[:],e.name,e.data.replace(DROPBEAR_OLD,DROPBEAR_NEW,1))
        rebuilt.append(e)
    maxino+=1; rebuilt.append(new_entry('usr/bin/nokia-tftp',tftp,0o100755,maxino))
    maxino+=1; rebuilt.append(new_entry('usr/bin/tftp',b'nokia-tftp',0o120777,maxino))
    maxino+=1; rebuilt.append(new_entry('usr/bin/nokia-scp',scp,0o100755,maxino))
    maxino+=1; rebuilt.append(new_entry('usr/bin/scp',b'nokia-scp',0o120777,maxino))
    maxino+=1; rebuilt.append(new_entry('TRAILER!!!',b'',0,maxino))
    archive=b''.join(build_entry(e) for e in rebuilt)
    if len(archive)>capacity:
        raise ValueError(f'patched initramfs {len(archive)} exceeds fixed cpio window {capacity}')
    out=bytearray(raw); out[start:next_nonzero]=archive+b'\0'*(capacity-len(archive))
    # Hard safety: linked bytes outside the archive window are byte-identical.
    if out[:start]!=raw[:start] or out[next_nonzero:]!=raw[next_nonzero:]: raise AssertionError('linked Image bytes moved')
    # Reparse exact result and prove paths/data/auth.
    _,_,check=find_archive(bytes(out)); cmap={e.name:e for e in check}
    if cmap['usr/bin/nokia-tftp'].data!=tftp or cmap['usr/bin/nokia-scp'].data!=scp: raise AssertionError('client data mismatch')
    if cmap['usr/bin/tftp'].data!=b'nokia-tftp' or cmap['usr/bin/scp'].data!=b'nokia-scp': raise AssertionError('client symlink mismatch')
    if DROPBEAR_NEW not in cmap['etc/init.d/dropbear'].data: raise AssertionError('Dropbear -B missing')
    return bytes(out),start,next_nonzero,removed,len(archive)

def patch_fit_blob(fit_blob:bytes,tftp:bytes,scp:bytes,recovery:bool,version:str):
    fit=Fdt(fit_blob); k=fit.node('/images/kernel-1')
    if cstr(k.get('compression'))!='lzma': raise ValueError('expected LZMA transition/recovery kernel')
    old=k.get('data'); assert old is not None
    raw=lzma.decompress(old,format=lzma.FORMAT_ALONE)
    raw2,start,end,removed,archive_len=patch_cpio(raw,tftp,scp,recovery)
    if len(raw2)!=len(raw): raise AssertionError('raw Linux Image size changed')
    filters=[{'id':lzma.FILTER_LZMA1,'dict_size':4*1024*1024,'lc':3,'lp':0,'pb':2,
              'mode':lzma.MODE_NORMAL,'nice_len':64,'mf':lzma.MF_BT4,'depth':0}]
    k.set('data',lzma.compress(raw2,format=lzma.FORMAT_ALONE,filters=filters))
    # Fix stale release provenance in transient FIT descriptions only.
    for _,n in fit.walk():
        for i,(name,val) in enumerate(n.props):
            if name=='description':
                for oldtag in (b'rc17fix3',b'rc17fix4',b'rc17fix5',b'rc18'):
                    if oldtag in val: val=val.replace(oldtag,version.encode('ascii'))
                n.props[i]=(name,val)
    hash_image(k)
    out=fit.build()
    return out,start,end,removed,archive_len,len(old),len(k.get('data') or b'')

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--kind',choices=('auto','manual','recovery'),required=True)
    ap.add_argument('--version',default='rc19')
    ap.add_argument('--client-dir',type=Path,default=HERE.parent/'recovery-clients-bin')
    ns=ap.parse_args(argv)
    tftp=(ns.client_dir/'nokia-tftp').read_bytes(); scp=(ns.client_dir/'nokia-scp').read_bytes()
    pins={'tftp':'2b6bbc51975e22f420565c42363821eb362936136b03f70a2a0cedee99c1641a','scp':'232a4ba7f8ae62922815bb12503fd7d09c3b4f40929d130475e467f0a597ac89'}
    if hashlib.sha256(tftp).hexdigest()!=pins['tftp'] or hashlib.sha256(scp).hexdigest()!=pins['scp']:
        raise SystemExit('ERROR: pinned RC7/RC15 AArch64 recovery client SHA mismatch')
    raw=ns.input.read_bytes()
    if len(raw)<8 or struct.unpack('>I',raw[:4])[0]!=FDT_MAGIC: raise SystemExit('ERROR: input does not start with FIT')
    old_fit_size=struct.unpack('>I',raw[4:8])[0]
    fit,start,end,removed,alen,oldkc,newkc=patch_fit_blob(raw[:old_fit_size],tftp,scp,ns.kind=='recovery',ns.version)
    if ns.kind=='auto':
        if len(fit)>0x800000: raise SystemExit('ERROR: patched auto FIT exceeds 8 MiB window')
        out=fit+b'\0'*(0x800000-len(fit))+raw[0x800000:]
    elif ns.kind=='manual':
        if len(fit)>len(raw): raise SystemExit('ERROR: patched manual FIT exceeds fixed bundle')
        out=fit+b'\0'*(len(raw)-len(fit))
    else: out=fit
    ns.output.write_bytes(out)
    print(f'PATCHED kind={ns.kind} fit={old_fit_size}->{len(fit)} file={len(raw)}->{len(out)} cpio_window=0x{start:x}..0x{end:x} archive={alen}')
    print(f'kernel_lzma={oldkc}->{newkc} removed_metadata={removed}')
    print('SHA256',hashlib.sha256(out).hexdigest())
    return 0
if __name__=='__main__': raise SystemExit(main())
