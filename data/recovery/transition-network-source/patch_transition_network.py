#!/usr/bin/env python3
"""Build-time transition/recovery network safety patcher for MedveFlasher.

SAFETY POLICY
-------------
LAN1 / the 2.5G port is intentionally excluded from every transition and
recovery environment.  It is considered unstable for recovery/control-plane
work and MUST NOT be used for stock->transition, manual transition, automatic
progress monitoring, RAM recovery, or restore traffic.  Use LAN2/LAN3/LAN4.

This patcher intentionally refuses production images.  For a transition or
recovery FIT it performs two independent changes:
  1. replaces the initramfs /etc/board.d/02_network with the pinned family
     template that exposes only LAN2/LAN3/LAN4 for Nokia;
  2. disables the 2500base-x MAC node in the DT and removes its OpenWrt netdev
     name/NVMEM binding, so the 2.5G interface cannot participate accidentally.

The built-in initramfs archive is patched size-preservingly inside the raw
kernel Image; the kernel is then re-compressed and FIT crc32/sha1 hashes are
recalculated.  Auto bundles keep the production tail byte-for-byte.
"""
from __future__ import annotations
import argparse, hashlib, lzma, struct, sys, zlib
from dataclasses import dataclass, field
from pathlib import Path

FDT_MAGIC=0xD00DFEED
FDT_BEGIN_NODE=1; FDT_END_NODE=2; FDT_PROP=3; FDT_NOP=4; FDT_END=9

def a4(n:int)->int: return (n+3)&~3

@dataclass
class Node:
    name:str
    props:list[tuple[str,bytes]]=field(default_factory=list)
    children:list['Node']=field(default_factory=list)
    def get(self,name:str)->bytes|None:
        for k,v in self.props:
            if k==name: return v
        return None
    def set(self,name:str,value:bytes)->None:
        for i,(k,v) in enumerate(self.props):
            if k==name:
                self.props[i]=(name,value); return
        self.props.append((name,value))
    def delete(self,name:str)->None:
        self.props=[(k,v) for k,v in self.props if k!=name]

class Fdt:
    def __init__(self, blob:bytes):
        self.blob=blob
        h=struct.unpack('>10I',blob[:40])
        (magic,self.totalsize,self.off_struct,self.off_strings,self.off_mem,
         self.version,self.last_comp,self.boot_cpuid,self.size_strings,self.size_struct)=h
        if magic!=FDT_MAGIC: raise ValueError('not FDT/FIT')
        self.strings=blob[self.off_strings:self.off_strings+self.size_strings]
        p=self.off_struct; end=self.off_struct+self.size_struct; stack:list[Node]=[]; root=None
        while p<end:
            tok=struct.unpack('>I',blob[p:p+4])[0]; p+=4
            if tok==FDT_BEGIN_NODE:
                q=blob.index(b'\0',p); name=blob[p:q].decode('utf-8','surrogateescape'); p=a4(q+1)
                n=Node(name)
                if stack: stack[-1].children.append(n)
                else: root=n
                stack.append(n)
            elif tok==FDT_END_NODE: stack.pop()
            elif tok==FDT_PROP:
                ln,noff=struct.unpack('>II',blob[p:p+8]); p+=8
                data=blob[p:p+ln]; p=a4(p+ln)
                q=self.strings.index(b'\0',noff); name=self.strings[noff:q].decode('ascii')
                stack[-1].props.append((name,data))
            elif tok==FDT_NOP: pass
            elif tok==FDT_END: break
            else: raise ValueError(f'bad FDT token {tok}')
        if root is None: raise ValueError('empty FDT')
        self.root=root
    def node(self,path:str)->Node:
        if path=='/': return self.root
        cur=self.root
        for part in path.strip('/').split('/'):
            cur=next((c for c in cur.children if c.name==part),None)
            if cur is None: raise KeyError(path)
        return cur
    def walk(self):
        def rec(n:Node,path:str):
            yield path,n
            for c in n.children:
                cp=(path.rstrip('/')+'/'+c.name) if path!='/' else '/'+c.name
                yield from rec(c,cp)
        yield from rec(self.root,'/')
    def build(self)->bytes:
        names=[]
        for _,n in self.walk():
            for k,_ in n.props:
                if k not in names: names.append(k)
        stab=bytearray(); noff={}
        for k in names:
            noff[k]=len(stab); stab += k.encode('ascii')+b'\0'
        s=bytearray()
        def emit(n:Node):
            nonlocal s
            s += struct.pack('>I',FDT_BEGIN_NODE)
            nb=n.name.encode('utf-8','surrogateescape')+b'\0'; s += nb; s += b'\0'*((-len(s))%4)
            for k,v in n.props:
                s += struct.pack('>III',FDT_PROP,len(v),noff[k]); s += v; s += b'\0'*((-len(s))%4)
            for c in n.children: emit(c)
            s += struct.pack('>I',FDT_END_NODE)
        emit(self.root); s += struct.pack('>I',FDT_END)
        mem=b'\0'*16
        off_mem=40; off_struct=a4(off_mem+len(mem)); pre=b'\0'*(off_struct-(off_mem+len(mem)))
        off_strings=off_struct+len(s); totalsize=off_strings+len(stab)
        hdr=struct.pack('>10I',FDT_MAGIC,totalsize,off_struct,off_strings,off_mem,
                        self.version,self.last_comp,self.boot_cpuid,len(stab),len(s))
        return hdr+mem+pre+bytes(s)+bytes(stab)

def cstr(b:bytes|None)->str:
    return '' if b is None else b.split(b'\0',1)[0].decode('ascii','replace')

def hash_image(node:Node)->None:
    data=node.get('data')
    if data is None: raise ValueError(f'image {node.name} has no data')
    for h in node.children:
        algo=cstr(h.get('algo'))
        if algo=='crc32': h.set('value',struct.pack('>I',zlib.crc32(data)&0xffffffff))
        elif algo=='sha1': h.set('value',hashlib.sha1(data).digest())

def find_cpio_entry(raw:bytes,name_wanted:str):
    pos=0
    while True:
        start=raw.find(b'070701',pos)
        if start<0: raise ValueError('newc initramfs not found')
        try:
            p=start; found=None; count=0; busy=False
            while True:
                if raw[p:p+6] not in (b'070701',b'070702'): raise ValueError
                hdr=raw[p:p+110]; p+=110
                vals=[int(hdr[6+i*8:14+i*8],16) for i in range(13)]
                filesize=vals[6]; namesize=vals[11]
                nb=raw[p:p+namesize]; p=a4(p+namesize)
                if not nb.endswith(b'\0'): raise ValueError
                name=nb[:-1].decode('utf-8','surrogateescape')
                dataoff=p; p=a4(p+filesize); count+=1
                if name=='bin/busybox': busy=True
                if name==name_wanted: found=(dataoff,filesize)
                if name=='TRAILER!!!':
                    if busy and count>100 and found: return found
                    break
        except Exception: pass
        pos=start+1

def patch_board_script(raw:bytes,template:bytes)->bytes:
    off,ln=find_cpio_entry(raw,'etc/board.d/02_network')
    if len(template)>ln: raise ValueError(f'network template {len(template)} > fixed initramfs slot {ln}')
    if b'lan1' in template.lower(): raise ValueError('policy template still references lan1')
    padded=template + b' '*(ln-len(template))
    out=bytearray(raw); out[off:off+ln]=padded
    if b'lan1' in out[off:off+ln].lower(): raise ValueError('lan1 survived board script patch')
    return bytes(out)

def patch_inner_dtb(blob:bytes)->bytes:
    f=Fdt(blob); candidates=[]
    for path,n in f.walk():
        if cstr(n.get('phy-mode'))=='2500base-x': candidates.append((path,n))
    if len(candidates)!=1: raise ValueError(f'expected exactly one 2500base-x node, got {[p for p,_ in candidates]}')
    path,n=candidates[0]
    old_name=cstr(n.get('openwrt,netdev-name'))
    if old_name!='lan1': raise ValueError(f'2500base-x node is not lan1: {path} name={old_name!r}')
    n.set('status',b'disabled\0')
    n.delete('openwrt,netdev-name')
    n.delete('nvmem-cell-names'); n.delete('nvmem-cells')
    out=f.build(); check=Fdt(out); cn=check.node(path)
    if cstr(cn.get('status'))!='disabled' or cn.get('openwrt,netdev-name') is not None:
        raise ValueError('2.5G disable verification failed')
    return out

def patch_fit(fit_blob:bytes,template:bytes,new_version:str)->bytes:
    fit=Fdt(fit_blob)
    k=fit.node('/images/kernel-1'); fdtn=fit.node('/images/fdt-1')
    comp=cstr(k.get('compression'))
    if comp!='lzma': raise ValueError(f'unsupported kernel compression {comp!r}')
    old_k=k.get('data'); old_dtb=fdtn.get('data')
    if old_k is None or old_dtb is None: raise ValueError('FIT image data missing')
    raw=lzma.decompress(old_k,format=lzma.FORMAT_ALONE)
    raw2=patch_board_script(raw,template)
    # Fixed deterministic LZMA1 parameters; dict matches the historical 4 MiB OpenWrt stream.
    filters=[{'id':lzma.FILTER_LZMA1,'dict_size':4*1024*1024,'lc':3,'lp':0,'pb':2,
              'mode':lzma.MODE_NORMAL,'nice_len':64,'mf':lzma.MF_BT4,'depth':0}]
    new_k=lzma.compress(raw2,format=lzma.FORMAT_ALONE,filters=filters)
    new_dtb=patch_inner_dtb(old_dtb)
    k.set('data',new_k); fdtn.set('data',new_dtb)
    # Release descriptions may include the previous release tag.
    for _,n in fit.walk():
        for i,(name,val) in enumerate(n.props):
            if name=='description' and b'rc17fix4' in val:
                n.props[i]=(name,val.replace(b'rc17fix4',new_version.encode('ascii')))
    desc=cstr(fdtn.get('description'))
    if '2.5G-disabled' not in desc:
        fdtn.set('description',(desc+'; transition/recovery 2.5G-disabled').encode('ascii')+b'\0')
    hash_image(k); hash_image(fdtn)
    out=fit.build()
    # Reparse and re-check image hashes.
    vf=Fdt(out)
    for p in ('/images/kernel-1','/images/fdt-1'):
        n=vf.node(p); data=n.get('data'); assert data is not None
        for h in n.children:
            algo=cstr(h.get('algo')); v=h.get('value')
            if algo=='crc32' and v!=struct.pack('>I',zlib.crc32(data)&0xffffffff): raise ValueError('crc verify')
            if algo=='sha1' and v!=hashlib.sha1(data).digest(): raise ValueError('sha1 verify')
    return out

def main(argv=None)->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--family',choices=('md','mf'),required=True)
    ap.add_argument('--kind',choices=('auto','manual','recovery'),required=True)
    ap.add_argument('--template-dir',type=Path,default=Path(__file__).resolve().parent)
    ap.add_argument('--version',default='rc17fix5')
    ns=ap.parse_args(argv)
    template=(ns.template_dir/f'shipped-{ns.family}-02_network.sh').read_bytes()
    raw=ns.input.read_bytes()
    if len(raw)<8 or struct.unpack('>I',raw[:4])[0]!=FDT_MAGIC: raise SystemExit('ERROR: input does not start with FIT')
    old_fit_size=struct.unpack('>I',raw[4:8])[0]
    old_fit=raw[:old_fit_size]
    new_fit=patch_fit(old_fit,template,ns.version)
    if ns.kind in ('auto','manual'):
        window=0x800000
        if len(new_fit)>window: raise SystemExit('ERROR: patched FIT exceeds fixed 8 MiB transition window')
        if ns.kind=='auto': out=new_fit+b'\0'*(window-len(new_fit))+raw[window:]
        else: out=new_fit+b'\0'*(len(raw)-len(new_fit))
    else:
        # Recovery FITs are standalone TFTP/boot images, not fixed 8 MiB windows.
        # Pin the new exact FIT size in release metadata instead of truncating or
        # weakening the LAN safety patch merely to preserve a historical file size.
        out=new_fit
    ns.output.write_bytes(out)
    print(f'PATCHED {ns.family} {ns.kind}: fit {old_fit_size} -> {len(new_fit)}; file {len(raw)} -> {len(out)}')
    print('SHA256',hashlib.sha256(out).hexdigest())
    return 0
if __name__=='__main__': raise SystemExit(main())
