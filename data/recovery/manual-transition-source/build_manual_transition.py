#!/usr/bin/env python3
from __future__ import annotations
import hashlib, lzma, struct, zlib
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR=Path(__file__).resolve().parent
KIT=SCRIPT_DIR.parents[2]
SRC=KIT/'data/transition-bundle.bin'
OUT=KIT/'data/transition-manual-bundle.bin'
CPIO_START=12575648
CPIO_END=21607252
WINDOW=0x800000

@dataclass
class CpioEntry:
    ino:int; mode:int; uid:int; gid:int; nlink:int; mtime:int; data:bytes
    devmajor:int; devminor:int; rdevmajor:int; rdevminor:int; name:str; check:int=0

def parse_cpio(raw:bytes)->list[CpioEntry]:
    out=[]; p=0
    while True:
        magic=raw[p:p+6]
        if magic not in (b'070701',b'070702'): raise ValueError(f'cpio magic at {p}')
        f=[int(raw[p+6+i*8:p+14+i*8],16) for i in range(13)]
        ino,mode,uid,gid,nlink,mtime,filesize,devmaj,devmin,rdevmaj,rdevmin,namesize,check=f
        q=p+110; name=raw[q:q+namesize-1].decode('utf-8'); q=(q+namesize+3)&~3
        data=raw[q:q+filesize]; p=(q+filesize+3)&~3
        if name=='TRAILER!!!': break
        out.append(CpioEntry(ino,mode,uid,gid,nlink,mtime,data,devmaj,devmin,rdevmaj,rdevmin,name,check))
    return out

def pack_cpio(entries:list[CpioEntry])->bytes:
    out=bytearray()
    trailer_mtime=max((e.mtime for e in entries), default=0)
    for e in entries+[CpioEntry(0,0,0,0,1,trailer_mtime,b'',0,0,0,0,'TRAILER!!!',0)]:
        name=e.name.encode()+b'\0'; data=e.data
        vals=(e.ino,e.mode,e.uid,e.gid,e.nlink,e.mtime,len(data),e.devmajor,e.devminor,e.rdevmajor,e.rdevminor,len(name),e.check)
        out += b'070701'+b''.join(f'{v & 0xffffffff:08x}'.encode() for v in vals)
        out += name
        out += b'\0' * ((-len(out)) & 3)
        out += data
        out += b'\0' * ((-len(out)) & 3)
    return bytes(out)

# Minimal FDT parser/serializer preserving order.
@dataclass
class Node:
    name:str
    props:list[tuple[str,bytes]]=field(default_factory=list)
    children:list['Node']=field(default_factory=list)

def parse_fdt(blob:bytes)->Node:
    h=struct.unpack('>10I',blob[:40]); magic,tot,os,ost,orm,ver,last,boot,ss,sst=h
    assert magic==0xd00dfeed
    strings=blob[ost:ost+ss]; sb=blob[os:os+sst]
    root=None; stack=[]; p=0
    while p<len(sb):
        tok=struct.unpack_from('>I',sb,p)[0]; p+=4
        if tok==1:
            e=sb.index(0,p); name=sb[p:e].decode(); p=(e+4)&~3
            n=Node(name)
            if stack: stack[-1].children.append(n)
            else: root=n
            stack.append(n)
        elif tok==2: stack.pop()
        elif tok==3:
            ln,no=struct.unpack_from('>II',sb,p); p+=8
            val=sb[p:p+ln]; p=(p+ln+3)&~3
            e=strings.index(0,no); pn=strings[no:e].decode()
            stack[-1].props.append((pn,val))
        elif tok==4: pass
        elif tok==9: break
        else: raise ValueError(tok)
    assert root is not None
    return root

def find_node(root:Node,path:str)->Node:
    n=root
    for part in [p for p in path.split('/') if p]:
        n=next(c for c in n.children if c.name==part)
    return n

def set_prop(n:Node,name:str,val:bytes):
    for i,(k,v) in enumerate(n.props):
        if k==name: n.props[i]=(k,val); return
    n.props.append((name,val))

def build_fdt(root:Node)->bytes:
    names=[]
    def collect(n):
        for k,_ in n.props:
            if k not in names: names.append(k)
        for c in n.children: collect(c)
    collect(root)
    strings=bytearray(); offs={}
    for k in names: offs[k]=len(strings); strings+=k.encode()+b'\0'
    sb=bytearray()
    def u32(x): return struct.pack('>I',x)
    def node(n):
        sb.extend(u32(1)); sb.extend(n.name.encode()+b'\0'); sb.extend(b'\0'*((-len(sb))&3))
        for k,v in n.props:
            sb.extend(u32(3)); sb.extend(u32(len(v))); sb.extend(u32(offs[k])); sb.extend(v); sb.extend(b'\0'*((-len(sb))&3))
        for c in n.children: node(c)
        sb.extend(u32(2))
    node(root); sb.extend(u32(9))
    mem=bytes(16)
    off_mem=40; off_struct=off_mem+len(mem); off_strings=off_struct+len(sb); total=off_strings+len(strings)
    hdr=struct.pack('>10I',0xd00dfeed,total,off_struct,off_strings,off_mem,17,16,0,len(strings),len(sb))
    return hdr+mem+bytes(sb)+bytes(strings)

def prop_text(n:Node,name:str)->str:
    return next(v for k,v in n.props if k==name).rstrip(b'\0').decode()

def extract_prop(n:Node,name:str)->bytes:
    return next(v for k,v in n.props if k==name)

# Read existing FIT and kernel.
full=SRC.read_bytes(); fit_total=struct.unpack('>I',full[4:8])[0]; fit=full[:fit_total]
root=parse_fdt(fit)
kern=find_node(root,'/images/kernel-1'); fdt=find_node(root,'/images/fdt-1')
compressed=extract_prop(kern,'data'); raw=lzma.decompress(compressed,format=lzma.FORMAT_AUTO)
old_archive=raw[CPIO_START:CPIO_END]
entries=parse_cpio(old_archive)
by={e.name:e for e in entries}

# Patch installer to accept a per-session expected SHA256 from the PC wizard.
installer=by['usr/sbin/nokia-ubi-installer'].data.decode()
needle="file_size() { wc -c < \"$1\" | tr -d ' '; }\nsha_file() { sha256sum \"$1\" | awk '{print $1}'; }\n"
insert="""file_size() { wc -c < \"$1\" | tr -d ' '; }\nsha_file() { sha256sum \"$1\" | awk '{print $1}'; }\n\nexpected_sysupgrade_sha() {\n    local expected\n    expected=\"${NOKIA_EXPECTED_SYSUPGRADE_SHA:-}\"\n    [ -n \"$expected\" ] || expected=\"$(cat /tmp/NOKIA_CUSTOM_SYSUPGRADE_SHA256 2>/dev/null || true)\"\n    [ -n \"$expected\" ] || expected=\"$SYSUPGRADE_SHA\"\n    case \"$expected\" in\n        *[!0-9a-fA-F]*|'') die 'invalid expected sysupgrade SHA256' ;;\n    esac\n    [ \"${#expected}\" -eq 64 ] || die 'invalid expected sysupgrade SHA256 length'\n    printf '%s\\n' \"$(printf '%s' \"$expected\" | tr 'A-F' 'a-f')\"\n}\n"""
assert needle in installer
installer=installer.replace(needle,insert,1)
installer=installer.replace("[ \"$(sha_file \"$image\")\" = \"$SYSUPGRADE_SHA\" ] || die 'production UBI sysupgrade SHA256 mismatch'", "[ \"$(sha_file \"$image\")\" = \"$(expected_sysupgrade_sha)\" ] || die 'selected UBI sysupgrade SHA256 mismatch'")
installer=installer.replace("log 'FULLFLASH: check -> format stock NAND as all-in-UBI -> embedded OpenWrt sysupgrade.'", "log 'FULLFLASH: check -> format stock NAND as all-in-UBI -> selected OpenWrt sysupgrade.'")
installer=installer.replace(
    '''    if [ "${NOKIA_AUTOMATIC_FULLFLASH:-0}" = 1 ]; then
        log 'AUTOMATIC MODE: CONFIRM FORMAT AND FLASH was accepted before the transition bundle was written.'
        log 'Proceeding without another interactive prompt.'
    else
''',
    '''    if [ "${NOKIA_PC_CONFIRMED_CUSTOM_FLASH:-0}" = 1 ]; then
        log 'PC WIZARD MODE: the selected image was validated and confirmed by the operator.'
        log 'Proceeding without another interactive prompt.'
    elif [ "${NOKIA_AUTOMATIC_FULLFLASH:-0}" = 1 ]; then
        log 'AUTOMATIC MODE: CONFIRM FORMAT AND FLASH was accepted before the transition bundle was written.'
        log 'Proceeding without another interactive prompt.'
    else
''',1)
installer=installer.replace(
    '''    if [ "${NOKIA_AUTOMATIC_FULLFLASH:-0}" = 1 ]; then
        log 'Automatic stage 2: authorization was already accepted on stock before reboot.'
    else
''',
    '''    if [ "${NOKIA_PC_CONFIRMED_CUSTOM_FLASH:-0}" = 1 ]; then
        log 'PC wizard mode: the selected image was validated and confirmed after transition boot.'
    elif [ "${NOKIA_AUTOMATIC_FULLFLASH:-0}" = 1 ]; then
        log 'Automatic stage 2: authorization was already accepted on stock before reboot.'
    else
''',1)
by['usr/sbin/nokia-ubi-installer'].data=installer.encode()

finish=by['usr/sbin/nokia-ubi-finish'].data.decode()
needle="log() { printf '%s\\n' \"$*\"; }\ndie() { printf 'ERROR: %s\\n' \"$*\" >&2; exit 1; }\nsha_file() { sha256sum \"$1\" | awk '{print $1}'; }\n"
insert="""log() { printf '%s\\n' \"$*\"; }\ndie() { printf 'ERROR: %s\\n' \"$*\" >&2; exit 1; }\nsha_file() { sha256sum \"$1\" | awk '{print $1}'; }\nexpected_sha() {\n    local expected\n    expected=\"${NOKIA_EXPECTED_SYSUPGRADE_SHA:-}\"\n    [ -n \"$expected\" ] || expected=\"$(cat /tmp/NOKIA_CUSTOM_SYSUPGRADE_SHA256 2>/dev/null || true)\"\n    [ -n \"$expected\" ] || expected=\"$EXPECTED_SHA\"\n    case \"$expected\" in *[!0-9a-fA-F]*|'') die 'invalid expected sysupgrade SHA256' ;; esac\n    [ \"${#expected}\" -eq 64 ] || die 'invalid expected sysupgrade SHA256 length'\n    printf '%s\\n' \"$(printf '%s' \"$expected\" | tr 'A-F' 'a-f')\"\n}\n"""
assert needle in finish
finish=finish.replace(needle,insert,1)
finish=finish.replace("[ \"$(sha_file \"$IMAGE\")\" = \"$EXPECTED_SHA\" ] || die 'production UBI sysupgrade SHA256 mismatch'", "SELECTED_SHA=\"$(expected_sha)\"\n[ \"$(sha_file \"$IMAGE\")\" = \"$SELECTED_SHA\" ] || die 'selected UBI sysupgrade SHA256 mismatch'")
finish=finish.replace('log "SHA256: $EXPECTED_SHA"','log "SHA256: $SELECTED_SHA"')
finish=finish.replace(
    '''    if [ "${NOKIA_AUTOMATIC_FULLFLASH:-0}" = 1 ]; then
        log 'Automatic stage 2 authorization inherited from the confirmed stock stage.'
        touch /tmp/NOKIA_FORMAT_AND_FLASH_CONFIRMED
    else
''',
    '''    if [ "${NOKIA_PC_CONFIRMED_CUSTOM_FLASH:-0}" = 1 ]; then
        log 'Custom image authorization received from the PC wizard after validation.'
        touch /tmp/NOKIA_FORMAT_AND_FLASH_CONFIRMED
    elif [ "${NOKIA_AUTOMATIC_FULLFLASH:-0}" = 1 ]; then
        log 'Automatic stage 2 authorization inherited from the confirmed stock stage.'
        touch /tmp/NOKIA_FORMAT_AND_FLASH_CONFIRMED
    else
''',1)
by['usr/sbin/nokia-ubi-finish'].data=finish.encode()

# Manual readiness service; no autonomous flash service symlink.
entries=[e for e in entries if e.name not in {'etc/rc.d/S99nokia-autoflash','etc/init.d/nokia-autoflash','usr/sbin/nokia-ubi-autoflash','installer/boot-autoflash.sh'}]
maxino=max(e.ino for e in entries)+1
mtime=max(e.mtime for e in entries)
def add(name,data,mode=0o100755,nlink=1):
    global maxino
    entries.append(CpioEntry(maxino,mode,0,0,nlink,mtime,data,0,0,0,0,name,0)); maxino+=1
manual_init=b'''#!/bin/sh /etc/rc.common\nSTART=99\n\nstart() {\n    printf '%s\\n' WAITING_FOR_CUSTOM_IMAGE > /tmp/NOKIA_MANUAL_STATE\n    touch /tmp/NOKIA_MANUAL_TRANSITION_READY\n    printf '%s\\n' 'NOKIA-MANUAL: transition ready; waiting for a sysupgrade image from the PC wizard.' | dd of=/dev/kmsg bs=4096 count=1 2>/dev/null || true\n}\n'''
add('etc/init.d/nokia-manual-ready',manual_init)
add('etc/rc.d/S99nokia-manual-ready',b'../init.d/nokia-manual-ready',0o120777)

# Replace profile status with manual-mode status and update motd.
if 'etc/profile.d/10-nokia-autoflash-status.sh' in by:
    by['etc/profile.d/10-nokia-autoflash-status.sh'].data=b'''#!/bin/ash\n[ -f /tmp/NOKIA_MANUAL_TRANSITION_READY ] || return 0\necho\necho '=== Nokia Router MedveFlasher manual transition ==='\necho 'State: waiting for the PC wizard to upload and validate a sysupgrade image.'\necho 'Do not run another installer and do not remove power.'\necho\n'''
if 'etc/motd' in by:
    motd=by['etc/motd'].data.decode('utf-8','replace')
    motd='Nokia Router MedveFlasher manual transition for Nokia XG-040G-MD\n\nNo automatic NAND formatting or sysupgrade is scheduled.\nThe PC wizard will upload, validate and start the selected image.\n\n'
    by['etc/motd'].data=motd.encode()
if 'lib/preinit/00_nokia_manual_installer' in by:
    by['lib/preinit/00_nokia_manual_installer'].data=b'''#!/bin/ash\nprintf '%s\\n' 'NOKIA-MANUAL: automatic stage 2 disabled; waiting for normal init and PC wizard.' | dd of=/dev/kmsg bs=4096 count=1 2>/dev/null || true\nexit 0\n'''
if 'installer/boot-manual.sh' in by:
    by['installer/boot-manual.sh'].data=b'''#!/bin/ash\nprintf '%s\\n' 'Manual transition: use the PC wizard to upload and validate sysupgrade.'\nexit 0\n'''
if 'installer/MANIFEST.txt' in by:
    by['installer/MANIFEST.txt'].data=b'''version=1.0.0-rc2-manual\nautoflash=disabled\nmanual_ready_marker=/tmp/NOKIA_MANUAL_TRANSITION_READY\ncustom_sysupgrade_path=/tmp/nokia-custom-sysupgrade.itb\ncustom_sysupgrade_sha=/tmp/NOKIA_CUSTOM_SYSUPGRADE_SHA256\ncheck_command=nokia-ubi-installer check /tmp/nokia-custom-sysupgrade.itb\nfullflash_command=nokia-ubi-installer fullflash /tmp/nokia-custom-sysupgrade.itb\nauthorization=accepted by PC wizard only after custom image validation\nfallback=manual transition FIT remains in UBI fit volume\n'''

new_archive=pack_cpio(entries)
if len(new_archive)>len(old_archive): raise SystemExit(f'new cpio too large {len(new_archive)} > {len(old_archive)}')
new_raw=raw[:CPIO_START]+new_archive+b'\0'*(len(old_archive)-len(new_archive))+raw[CPIO_END:]
assert len(new_raw)==len(raw)
new_compressed=lzma.compress(new_raw,format=lzma.FORMAT_ALONE,preset=6)

# Update FIT data, hashes and descriptions.
set_prop(root,'description',b'Nokia Router MedveFlasher manual transition\0')
set_prop(kern,'description',b'ARM64 OpenWrt Nokia Router MedveFlasher manual transition\0')
set_prop(kern,'data',new_compressed)
for c in kern.children:
    algo=prop_text(c,'algo')
    if algo=='crc32': set_prop(c,'value',struct.pack('>I',zlib.crc32(new_compressed)&0xffffffff))
    elif algo=='sha1': set_prop(c,'value',hashlib.sha1(new_compressed).digest())
new_fit=build_fdt(root)
if len(new_fit)>WINDOW: raise SystemExit(f'FIT too large {len(new_fit)}')
manual=new_fit+b'\0'*(WINDOW-len(new_fit))
OUT.write_bytes(manual)
print('old fit',fit_total,'new fit',len(new_fit),'old kernel',len(compressed),'new kernel',len(new_compressed),'cpio',len(new_archive),'bundle',len(manual))
print('fit sha',hashlib.sha256(new_fit).hexdigest())
print('window sha',hashlib.sha256(manual[:WINDOW]).hexdigest())
print('bundle sha',hashlib.sha256(manual).hexdigest())
