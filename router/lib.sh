#!/bin/ash

EXPECTED_BOOTCMD='flash read 0xc0000 0x800000 0x85000000; bootm 0x85000000'

log() {
    printf '%s\n' "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

mtd_index() {
    awk -v wanted="$1" '$4 == "\"" wanted "\"" { sub(":", "", $1); print $1; exit }' /proc/mtd
}

mtd_size_hex() {
    awk -v wanted="$1" '$4 == "\"" wanted "\"" { print $2; exit }' /proc/mtd
}

require_partition() {
    name="$1"
    index="$2"
    size="$3"
    actual_index="$(mtd_index "$name")"
    actual_size="$(mtd_size_hex "$name")"
    [ "$actual_index" = "$index" ] || die "$name must be $index, got ${actual_index:-missing}"
    [ "$actual_size" = "$size" ] || die "$name size must be $size, got ${actual_size:-missing}"
}

verify_stock_layout() {
    [ -r /proc/mtd ] || die '/proc/mtd is unavailable'
    require_partition bootloader mtd0 00080000
    require_partition romfile mtd1 00040000
    require_partition kernel mtd2 003af6da
    require_partition rootfs mtd3 01cc0000
    require_partition kernel_slave mtd4 00480000
    require_partition rootfs_slave mtd5 02400000
    require_partition bosa mtd6 00040000
    require_partition ri mtd7 00040000
    require_partition flag mtd8 00040000
    require_partition flagback mtd9 00040000
    require_partition config mtd10 00a00000
    require_partition data mtd11 080e0000
    require_partition oopsfs mtd12 00400000
    require_partition log mtd13 00a00000
    require_partition nsb_master mtd14 02880000
    require_partition nsb_slave mtd15 02880000
    require_partition all_flash mtd16 0eba0000
}

file_size() {
    wc -c < "$1" | tr -d ' '
}

sha_file() {
    sha256sum "$1" | awk '{print $1}'
}

readback_sha() {
    device="$1"
    length="$2"
    blocks=$(( (length + 4095) / 4096 ))
    dd if="$device" bs=4096 count="$blocks" 2>/dev/null | \
        head -c "$length" | sha256sum | awk '{print $1}'
}

verify_magic() {
    file="$1"
    expected="$2"
    actual="$(dd if="$file" bs=1 count=4 2>/dev/null | od -An -tx1 | tr -d ' \n')"
    [ "$actual" = "$expected" ] || die "$file magic is $actual, expected $expected"
}

verify_env_bootcmd() {
    env_file="$1"
    count="$(
        dd if="$env_file" bs=16384 skip=7 count=1 2>/dev/null | \
            tr '\000' '\n' | \
            awk -v expected="bootcmd=$EXPECTED_BOOTCMD" '$0 == expected { count++ } END { print count + 0 }'
    )"
    [ "$count" -eq 1 ] || die 'U-Boot env must contain exactly one expected OpenWrt bootcmd'
}

verify_bundle() {
    bundle="$1"
    [ -d "$bundle" ] || die "bundle directory not found: $bundle"
    for file in \
        factory-kernel.bin \
        factory-rootfs.bin \
        OpenWrt.mtd2.u-boot-env.bin \
        OPENWRT_SHA256SUMS.txt \
        BUNDLE_INFO.txt \
        SHA256SUMS \
        SKYHIGH_NAND_CONFIRMED.txt; do
        [ -f "$bundle/$file" ] || die "missing bundle file: $file"
    done

    grep -qx 'SkyHigh ML02G300WHI00' "$bundle/SKYHIGH_NAND_CONFIRMED.txt" || \
        die 'SkyHigh NAND confirmation marker is invalid'

    command_exists sha256sum || die 'sha256sum is required'
    (
        cd "$bundle" || exit 1
        sha256sum -c SHA256SUMS
    ) || die 'bundle SHA-256 verification failed'

    kernel_size="$(file_size "$bundle/factory-kernel.bin")"
    rootfs_size="$(file_size "$bundle/factory-rootfs.bin")"
    env_size="$(file_size "$bundle/OpenWrt.mtd2.u-boot-env.bin")"

    [ "$kernel_size" -gt 0 ] || die 'factory kernel is empty'
    [ "$kernel_size" -le 8388608 ] || die 'factory kernel exceeds the 0x800000-byte limit'
    [ "$rootfs_size" -gt 0 ] || die 'factory rootfs is empty'
    [ "$rootfs_size" -le 135135232 ] || die 'factory rootfs exceeds the 0x80e0000-byte limit'
    [ "$env_size" -eq 131072 ] || die 'U-Boot env partition must be exactly 131072 bytes'

    verify_magic "$bundle/factory-kernel.bin" d00dfeed
    verify_magic "$bundle/factory-rootfs.bin" 55424923
    verify_env_bootcmd "$bundle/OpenWrt.mtd2.u-boot-env.bin"
}

verify_backup_dir() {
    backup="$1"
    [ -d "$backup" ] || die "backup directory not found: $backup"
    for file in \
        proc_mtd.txt \
        SHA256SUMS.txt \
        mtd0_bootloader.bin.gz \
        mtd16_all_flash.bin.gz \
        bosa.bin \
        ri.bin; do
        [ -f "$backup/$file" ] || die "missing backup file: $file"
    done

    [ "$(file_size "$backup/bosa.bin")" -eq 262144 ] || die 'bosa.bin has an unexpected size'
    [ "$(file_size "$backup/ri.bin")" -eq 262144 ] || die 'ri.bin has an unexpected size'

    command_exists gzip || die 'gzip is required to verify backup archives'
    command_exists sha256sum || die 'sha256sum is required to verify backup files'

    (
        cd "$backup" || exit 1
        sha256sum -c SHA256SUMS.txt
    ) || die 'backup SHA-256 verification failed'

    gzip -t "$backup/mtd0_bootloader.bin.gz" || die 'bootloader backup gzip test failed'
    gzip -t "$backup/mtd16_all_flash.bin.gz" || die 'all_flash backup gzip test failed'

    bootloader_size="$(gzip -dc "$backup/mtd0_bootloader.bin.gz" | wc -c | tr -d ' ')"
    all_flash_size="$(gzip -dc "$backup/mtd16_all_flash.bin.gz" | wc -c | tr -d ' ')"
    [ "$bootloader_size" -eq 524288 ] || die 'bootloader backup has an unexpected decompressed size'
    [ "$all_flash_size" -eq 247070720 ] || die 'all_flash backup has an unexpected decompressed size'
}

reject_fudan_if_detected() {
    if dmesg 2>/dev/null | grep -qi -E 'fudan|fm25g02b'; then
        die 'FudanMicro NAND detected; this experimental installer supports only SkyHigh NAND'
    fi
}

report_nand_detection() {
    if dmesg 2>/dev/null | grep -qi -E 'skyhigh|ml02g300whi00'; then
        log 'SkyHigh ML02G300WHI00 signature found in kernel log.'
    else
        log 'WARNING: kernel log does not positively identify SkyHigh NAND.'
        log 'The physical chip marking and bundle confirmation remain mandatory.'
    fi
}
