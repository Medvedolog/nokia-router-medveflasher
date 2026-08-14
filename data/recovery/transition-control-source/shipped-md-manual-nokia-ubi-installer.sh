#!/bin/ash
set -u
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077

PRELOADER=/installer/openwrt-airoha-an7581-nokia_xg-040g-md-ubi-preloader.bin
FIP=/installer/openwrt-airoha-an7581-nokia_xg-040g-md-ubi-bl31-uboot-ethfix.fip
PRELOADER_SHA='6c3b2339d036340396730a13adfe35c0d2a4dddedeffb6f9965a24e0c7908808'
FIP_SHA='9c29cdbcc3f9c00070cc72262c83dcd1eb212f89f6fb84806ad8657eadec2b8b'
SYSUPGRADE_SHA='c6f06fcf4d155201aad3347cb0558ed11319be24f82d44106a061406d23dda03'
DEFAULT_SYSUPGRADE='openwrt-airoha-an7581-nokia_xg-040g-md-ubi-squashfs-sysupgrade.itb'
EMBEDDED_OPENWRT_SYSUPGRADE='/tmp/nokia-embedded-openwrt-sysupgrade.itb'
EMBEDDED_OPENWRT_SYSUPGRADE_SIZE=13226255
EMBEDDED_OPENWRT_SYSUPGRADE_OFFSET=0x8c0000
EMBEDDED_OPENWRT_SYSUPGRADE_SHA='c6f06fcf4d155201aad3347cb0558ed11319be24f82d44106a061406d23dda03'
BL2_SIZE=131072
BL2_OFFSET=2048
FF_2K_SHA='d0ff1b294b5288d1ae1421eadf5b2d38a8752b76d472ff30bed9028e25b1c5b8'
BL2_EXPECTED_SHA='6f9c928bad500de0339bbfdfa354c17a7ac044f96c913f3a01301971d6cd659d'
ZERO_256K_SHA='8a39d2abd3999ab73c34db2476849cddf303ce389b35826850f9a700589b4a90'
FF_256K_SHA='3b874d3ba46c638fc3094f8e92fb744ca974893873f8885f54e23760f9b6311b'
LOG=/tmp/nokia-ubi-installer.log
WORK=/tmp/nokia-ubi-installer

kmsg_line() {
    printf '%s\n' "$1" | dd of=/dev/kmsg bs=4096 count=1 2>/dev/null || true
}

log() {
    printf '%s\n' "$*" | tee -a "$LOG"
    kmsg_line "NOKIA-UBI-INSTALLER: $*"
}

die() {
    log "ERROR: $*"
    printf '%s\n' "$*" > /tmp/NOKIA_UBI_INSTALL_FAILED
    exit 1
}

critical() {
    log "CRITICAL: $*"
    log 'The stock layout may already be destroyed. Do not power off or reboot blindly.'
    log 'Keep this initramfs running and use UART plus the verified backup if recovery is required.'
    printf '%s\n' "$*" > /tmp/NOKIA_UBI_INSTALL_FAILED
    exit 1
}

file_size() { wc -c < "$1" | tr -d ' '; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }

expected_sysupgrade_sha() {
    local expected
    expected="${NOKIA_EXPECTED_SYSUPGRADE_SHA:-}"
    [ -n "$expected" ] || expected="$(cat /tmp/NOKIA_CUSTOM_SYSUPGRADE_SHA256 2>/dev/null || true)"
    [ -n "$expected" ] || expected="$SYSUPGRADE_SHA"
    case "$expected" in
        *[!0-9a-fA-F]*|'') die 'invalid expected sysupgrade SHA256' ;;
    esac
    [ "${#expected}" -eq 64 ] || die 'invalid expected sysupgrade SHA256 length'
    printf '%s\n' "$(printf '%s' "$expected" | tr 'A-F' 'a-f')"
}

mtd_name() {
    awk -v wanted="\"$1\"" '$4 == wanted { sub(":", "", $1); print $1; exit }' /proc/mtd
}

mtd_dev() {
    local idx
    idx="$(mtd_name "$1")"
    [ -n "$idx" ] || return 1
    printf '/dev/%s\n' "$idx"
}

mtd_ro() {
    local idx
    idx="$(mtd_name "$1")"
    [ -n "$idx" ] || return 1
    if [ -e "/dev/${idx}ro" ]; then
        printf '/dev/%sro\n' "$idx"
    else
        printf '/dev/%s\n' "$idx"
    fi
}

mtd_num() {
    local idx
    idx="$(mtd_name "$1")" || return 1
    printf '%s\n' "${idx#mtd}"
}

require_mtd() {
    local label="$1" expected="$2" idx actual
    idx="$(mtd_name "$label")"
    [ -n "$idx" ] || die "missing MTD label: $label"
    actual="$(cat "/sys/class/mtd/$idx/size" 2>/dev/null || true)"
    [ "$actual" = "$expected" ] || die "$label size is ${actual:-unknown}, expected $expected"
    log "[OK] $idx label=$label size=$actual"
}

ubi_mknod() {
    local base="$1" devinfo major minor
    base="${base##*/}"
    [ -e "/dev/$base" ] && return 0
    [ -r "/sys/class/ubi/$base/dev" ] || return 1
    devinfo="$(cat "/sys/class/ubi/$base/dev")"
    major="${devinfo%%:*}"
    minor="${devinfo##*:}"
    mknod "/dev/$base" c "$major" "$minor"
}

find_ubi_for_mtd() {
    local wanted="$1" path
    for path in /sys/class/ubi/ubi[0-9]*; do
        [ -r "$path/mtd_num" ] || continue
        [ "$(cat "$path/mtd_num")" = "$wanted" ] || continue
        basename "$path"
        return 0
    done
    return 1
}

volume_name_at_id() {
    local path
    path="/sys/class/ubi/${1}_${2}/name"
    [ -r "$path" ] || return 1
    cat "$path"
}

layout_complete() {
    local ubi="$1"
    [ "$(volume_name_at_id "$ubi" 0 2>/dev/null || true)" = ubootenv ] || return 1
    [ "$(volume_name_at_id "$ubi" 1 2>/dev/null || true)" = ubootenv2 ] || return 1
    [ "$(volume_name_at_id "$ubi" 2 2>/dev/null || true)" = bosa ] || return 1
    [ "$(volume_name_at_id "$ubi" 3 2>/dev/null || true)" = ri ] || return 1
    [ "$(volume_name_at_id "$ubi" 4 2>/dev/null || true)" = fip ] || return 1
    [ "$(volume_name_at_id "$ubi" 5 2>/dev/null || true)" = fit ] || return 1
    return 0
}

readback_sha() {
    local dev="$1" length="$2"
    dd if="$dev" bs=4096 count=$(( (length + 4095) / 4096 )) 2>/dev/null | \
        head -c "$length" | sha256sum | awk '{print $1}'
}

validate_board_data() {
    local file="$1" name="$2" size hash
    size="$(file_size "$file")"
    [ "$size" -eq 262144 ] || die "$name size is $size, expected 262144"
    hash="$(sha_file "$file")"
    [ "$hash" != "$ZERO_256K_SHA" ] || die "$name is all-zero"
    [ "$hash" != "$FF_256K_SHA" ] || die "$name is all-FF"
    log "[OK] $name SHA256=$hash"
}

check_board() {
    [ "$(id -u)" = 0 ] || die 'root privileges are required'
    [ -r /tmp/sysinfo/board_name ] || die 'board_name is unavailable'
    [ "$(cat /tmp/sysinfo/board_name)" = 'nokia,xg-040g-md-ubi' ] || \
        die "unexpected board: $(cat /tmp/sysinfo/board_name)"
    tr '\000' '\n' < /proc/device-tree/compatible 2>/dev/null | grep -qx 'nokia,xg-040g-md-ubi' || \
        die 'unexpected device-tree compatible'
    log '[OK] board=nokia,xg-040g-md-ubi'
}

check_nand() {
    local evidence file identity cached
    mkdir -p "$WORK"
    if [ -r /tmp/NOKIA_NAND_IDENTITY ]; then
        cached="$(cat /tmp/NOKIA_NAND_IDENTITY 2>/dev/null || true)"
        case "$cached" in
            skyhigh) log '[OK] SkyHigh ML02G300WHI00 identity retained from the pre-format check.'; return 0 ;;
            fudan) die 'FudanMicro FM25G02B NAND is not supported by this U-Boot' ;;
            unknown) log 'WARNING: NAND identity remains unknown from the pre-format check.'; return 0 ;;
        esac
    fi
    evidence="$WORK/nand-identity.txt"
    : > "$evidence"
    dmesg 2>/dev/null | grep -v 'NOKIA-' >> "$evidence" || true
    for file in \
        /sys/class/mtd/mtd*/device/name \
        /sys/class/mtd/mtd*/device/model \
        /sys/class/mtd/mtd*/device/modalias \
        /sys/class/mtd/mtd*/device/uevent \
        /sys/bus/spi/devices/*/modalias \
        /sys/bus/spi/devices/*/uevent \
        /proc/nand /proc/spi_nand /proc/driver/nand /proc/driver/spi_nand; do
        [ -r "$file" ] || continue
        printf '\n--- %s ---\n' "$file" >> "$evidence"
        cat "$file" >> "$evidence" 2>/dev/null || true
    done

    if grep -qi -E 'fm25g02b' "$evidence"; then
        identity=fudan
        printf '%s\n' "$identity" > /tmp/NOKIA_NAND_IDENTITY
        die 'FudanMicro FM25G02B NAND is not supported by this U-Boot'
    fi
    if grep -qi -E 'ml02g300whi00' "$evidence"; then
        identity=skyhigh
        printf '%s\n' "$identity" > /tmp/NOKIA_NAND_IDENTITY
        log '[OK] SkyHigh ML02G300WHI00 explicitly detected.'
        return 0
    fi

    identity=unknown
    printf '%s\n' "$identity" > /tmp/NOKIA_NAND_IDENTITY
    log 'WARNING: the stock/mainline kernel did not expose the SPI-NAND model string.'
    log 'WARNING: Fudan was not detected, but SkyHigh cannot be proven from userspace.'
    log 'WARNING: unidentified NAND accepted after exact board/MTD/geometry checks; explicit Fudan remains blocked.'
}

check_geometry() {
    local bl2 ibu
    require_mtd all_flash 268435456
    require_mtd bl2 131072
    require_mtd ibu 268304384
    bl2="$(mtd_name bl2)"
    ibu="$(mtd_name ibu)"
    [ "$(cat "/sys/class/mtd/$bl2/erasesize")" = 131072 ] || die 'unexpected BL2 erase size'
    [ "$(cat "/sys/class/mtd/$ibu/erasesize")" = 131072 ] || die 'unexpected NAND erase size'
    [ "$(cat "/sys/class/mtd/$ibu/writesize")" = 2048 ] || die 'unexpected NAND write size'
    log '[OK] NAND geometry: erase=131072 write=2048.'
}

check_tools() {
    local cmd
    for cmd in awk basename cat dd dmesg grep head hexdump id mkdir mknod mount mtd rm sed sha256sum sync tee touch tr ubidetach ubiformat ubiattach ubimkvol ubinfo ubiupdatevol wc; do
        command -v "$cmd" >/dev/null 2>&1 || die "required command is missing: $cmd"
    done
    log '[OK] Required MTD/UBI tools are present.'
}

check_payloads() {
    local preloader_size fip_size
    [ -s "$PRELOADER" ] || die 'preloader payload is missing'
    [ -s "$FIP" ] || die 'ETH-fixed FIP payload is missing'
    [ "$(sha_file "$PRELOADER")" = "$PRELOADER_SHA" ] || die 'preloader SHA256 mismatch'
    [ "$(sha_file "$FIP")" = "$FIP_SHA" ] || die 'FIP SHA256 mismatch'
    preloader_size="$(file_size "$PRELOADER")"
    fip_size="$(file_size "$FIP")"
    [ "$preloader_size" -le $((BL2_SIZE - BL2_OFFSET)) ] || \
        die 'preloader plus mandatory 0x800 prefix does not fit BL2 partition'
    [ "$fip_size" -le 1048576 ] || die 'FIP exceeds reserved 1 MiB volume'
    log "[OK] preloader size=$preloader_size SHA256=$PRELOADER_SHA"
    log "[OK] ETH-fixed FIP size=$fip_size SHA256=$FIP_SHA"
}

prepare_bl2_image() {
    local size prefix_sha payload_sha payload_blocks preloader_size
    BL2_IMAGE="$WORK/bl2-partition.bin"
    rm -f "$BL2_IMAGE"

    dd if=/dev/zero bs="$BL2_SIZE" count=1 2>/dev/null | \
        tr '\000' '\377' > "$BL2_IMAGE" || die 'cannot create FF-filled BL2 partition image'
    dd if="$PRELOADER" of="$BL2_IMAGE" bs="$BL2_OFFSET" seek=1 conv=notrunc 2>/dev/null || \
        die 'cannot insert raw preloader at physical BL2 offset 0x800'

    size="$(file_size "$BL2_IMAGE")"
    [ "$size" -eq "$BL2_SIZE" ] || die "generated BL2 image size is $size, expected $BL2_SIZE"

    prefix_sha="$(dd if="$BL2_IMAGE" bs="$BL2_OFFSET" count=1 2>/dev/null | sha256sum | awk '{print $1}')"
    [ "$prefix_sha" = "$FF_2K_SHA" ] || die 'generated BL2 0x800 prefix is not all-FF'

    preloader_size="$(file_size "$PRELOADER")"
    payload_blocks=$(( (preloader_size + BL2_OFFSET - 1) / BL2_OFFSET ))
    payload_sha="$(dd if="$BL2_IMAGE" bs="$BL2_OFFSET" skip=1 count="$payload_blocks" 2>/dev/null | \
        head -c "$preloader_size" | sha256sum | awk '{print $1}')"
    [ "$payload_sha" = "$PRELOADER_SHA" ] || die 'generated BL2 image does not contain the exact preloader at offset 0x800'

    BL2_IMAGE_SHA="$(sha_file "$BL2_IMAGE")"
    [ "$BL2_IMAGE_SHA" = "$BL2_EXPECTED_SHA" ] || die 'complete generated BL2 image SHA256 mismatch'
    log "[OK] BL2 partition image: size=$BL2_SIZE prefix=0x800 preloader_offset=0x800 SHA256=$BL2_IMAGE_SHA"
}

read_board_data() {
    local all_ro
    all_ro="$(mtd_ro all_flash)" || die 'all_flash read device is missing'
    mkdir -p "$WORK"
    dd if="$all_ro" of="$WORK/bosa.bin" bs=131072 skip=654 count=2 2>/dev/null || die 'cannot read bosa at 0x51c0000'
    dd if="$all_ro" of="$WORK/ri.bin" bs=131072 skip=656 count=2 2>/dev/null || die 'cannot read ri at 0x5200000'
    validate_board_data "$WORK/bosa.bin" bosa
    validate_board_data "$WORK/ri.bin" ri
}

current_fit_size() {
    local all_ro hex size
    all_ro="$(mtd_ro all_flash)" || return 1
    [ "$(dd if="$all_ro" bs=1 skip=$((0xc0000)) count=4 2>/dev/null | hexdump -v -e '4/1 "%02x"')" = d00dfeed ] || return 1
    hex="$(dd if="$all_ro" bs=1 skip=$((0xc0000 + 4)) count=4 2>/dev/null | hexdump -v -e '4/1 "%02x"')"
    case "$hex" in ''|*[!0-9a-fA-F]*) return 1 ;; esac
    size=$((0x$hex))
    [ "$size" -gt 1048576 ] && [ "$size" -le 8388608 ] || return 1
    printf '%s\n' "$size"
}

capture_current_fit() {
    local all_ro fit_size blocks
    all_ro="$(mtd_ro all_flash)" || die 'all_flash read device is missing'
    fit_size="$(current_fit_size)" || die 'installer FIT is not readable at stock offset 0xc0000'
    blocks=$(( (fit_size + 4095) / 4096 ))
    dd if="$all_ro" of="$WORK/installer-padded.itb" bs=4096 skip=192 count="$blocks" 2>/dev/null || \
        die 'cannot copy running installer FIT into RAM'
    head -c "$fit_size" "$WORK/installer-padded.itb" > "$WORK/installer.itb" || die 'cannot trim installer FIT'
    rm -f "$WORK/installer-padded.itb"
    [ "$(dd if="$WORK/installer.itb" bs=1 count=4 2>/dev/null | hexdump -v -e '4/1 "%02x"')" = d00dfeed ] || \
        die 'captured installer FIT magic mismatch'
    log "[OK] captured installer FIT size=$fit_size SHA256=$(sha_file "$WORK/installer.itb")"
}

has_ubi_header_near_start() {
    local ibu_ro block magic
    ibu_ro="$(mtd_ro ibu)" || return 1
    block=0
    while [ "$block" -lt 64 ]; do
        magic="$(dd if="$ibu_ro" bs=131072 skip="$block" count=1 2>/dev/null | head -c 4 | hexdump -v -e '4/1 "%02x"')"
        [ "$magic" = 55424923 ] && return 0
        block=$((block + 1))
    done
    return 1
}

check_sysupgrade() {
    local image="$1"
    [ -f "$image" ] || die "sysupgrade image not found: $image"
    [ "$(dd if="$image" bs=1 count=4 2>/dev/null | hexdump -v -e '4/1 "%02x"')" = d00dfeed ] || \
        die 'sysupgrade image is not FIT'
    command -v sysupgrade >/dev/null 2>&1 || die 'sysupgrade command is missing'
    log "Testing only: sysupgrade -T $image"
    sysupgrade -T "$image" || die 'UBI sysupgrade image was rejected'
    log '[OK] matching UBI sysupgrade image accepted; nothing was written.'
}

capture_embedded_openwrt_sysupgrade() {
    local all_ro blocks
    if [ -f "$EMBEDDED_OPENWRT_SYSUPGRADE" ] && [ "$(file_size "$EMBEDDED_OPENWRT_SYSUPGRADE")" -eq "$EMBEDDED_OPENWRT_SYSUPGRADE_SIZE" ] && \
       [ "$(sha_file "$EMBEDDED_OPENWRT_SYSUPGRADE")" = "$EMBEDDED_OPENWRT_SYSUPGRADE_SHA" ]; then
        printf '%s\n' "$EMBEDDED_OPENWRT_SYSUPGRADE"
        return 0
    fi
    all_ro="$(mtd_ro all_flash)" || return 1
    blocks=$(( (EMBEDDED_OPENWRT_SYSUPGRADE_SIZE + 131071) / 131072 ))
    rm -f "$EMBEDDED_OPENWRT_SYSUPGRADE"
    dd if="$all_ro" bs=131072 skip=$((EMBEDDED_OPENWRT_SYSUPGRADE_OFFSET / 131072)) count="$blocks" 2>/dev/null | \
        head -c "$EMBEDDED_OPENWRT_SYSUPGRADE_SIZE" > "$EMBEDDED_OPENWRT_SYSUPGRADE" || return 1
    [ "$(file_size "$EMBEDDED_OPENWRT_SYSUPGRADE")" -eq "$EMBEDDED_OPENWRT_SYSUPGRADE_SIZE" ] || { rm -f "$EMBEDDED_OPENWRT_SYSUPGRADE"; return 1; }
    [ "$(sha_file "$EMBEDDED_OPENWRT_SYSUPGRADE")" = "$EMBEDDED_OPENWRT_SYSUPGRADE_SHA" ] || { rm -f "$EMBEDDED_OPENWRT_SYSUPGRADE"; return 1; }
    [ "$(dd if="$EMBEDDED_OPENWRT_SYSUPGRADE" bs=1 count=4 2>/dev/null | hexdump -v -e '4/1 "%02x"')" = d00dfeed ] || { rm -f "$EMBEDDED_OPENWRT_SYSUPGRADE"; return 1; }
    printf '%s\n' "$EMBEDDED_OPENWRT_SYSUPGRADE"
}

resolve_sysupgrade() {
    local requested="${1:-}" image
    if [ "$requested" = embedded-openwrt-sysupgrade ]; then
        capture_embedded_openwrt_sysupgrade
        return $?
    fi
    if [ -n "$requested" ]; then
        [ -f "$requested" ] || return 1
        printf '%s\n' "$requested"
        return 0
    fi
    image="$(capture_embedded_openwrt_sysupgrade 2>/dev/null || true)"
    if [ -n "$image" ]; then
        printf '%s\n' "$image"
        return 0
    fi
    return 1
}

base_check() {
    : > "$LOG"
    check_board
    check_nand
    check_geometry
    check_tools
    check_payloads
    if has_ubi_header_near_start; then
        log 'NOTICE: UBI EC header detected near the start of the target region.'
    else
        log '[OK] no UBI EC header detected in the first 64 target eraseblocks.'
    fi
    fit_size="$(current_fit_size 2>/dev/null || true)"
    if [ -n "$fit_size" ]; then
        log "[OK] current installer FIT is visible at physical offset 0xc0000, totalsize=$fit_size."
    else
        log 'NOTICE: no raw installer FIT found at 0xc0000; this can be normal after completed migration.'
    fi
}

run_check() {
    local requested="${1:-}" image
    image="$(resolve_sysupgrade "$requested" 2>/dev/null || true)"
    [ -z "$requested" ] || [ -n "$image" ] || die "cannot resolve requested OpenWrt sysupgrade image: $requested"
    base_check
    prepare_bl2_image
    if ! has_ubi_header_near_start; then
        read_board_data
    fi
    [ -z "$image" ] || { [ "$(sha_file "$image")" = "$(expected_sysupgrade_sha)" ] || die 'selected UBI sysupgrade SHA256 mismatch'; check_sysupgrade "$image"; }
    log ''
    log 'CHECK PASSED. No erase, format, UBI attach or NAND write was performed.'
    log 'To start the complete operation: nokia-ubi-installer fullflash embedded-openwrt-sysupgrade'
}

attach_existing() {
    local ibu ibu_num ubi
    ibu="$(mtd_dev ibu)" || die 'ibu device is missing'
    ibu_num="$(mtd_num ibu)" || die 'cannot resolve ibu MTD number'
    ubi="$(find_ubi_for_mtd "$ibu_num" 2>/dev/null || true)"
    if [ -z "$ubi" ]; then
        ubiattach -p "$ibu" >/tmp/nokia-ubiattach.log 2>&1 || {
            cat /tmp/nokia-ubiattach.log >&2 2>/dev/null || true
            die 'target region is not attachable as UBI'
        }
        ubi="$(find_ubi_for_mtd "$ibu_num" 2>/dev/null || true)"
    fi
    [ -n "$ubi" ] || die 'attached UBI device was not found'
    ubi_mknod "$ubi" || die "cannot create /dev/$ubi"
    layout_complete "$ubi" || die "UBI layout on $ubi is incomplete or has unexpected volume IDs"
    printf '%s\n' "$ubi" > /tmp/NOKIA_UBI_DEVICE
    cat > /tmp/NOKIA_UBI_INSTALL_COMPLETE <<EOF
status=complete
ubi=$ubi
preloader_sha256=$PRELOADER_SHA
fip_sha256=$FIP_SHA
EOF
    log "[OK] complete Nokia UBI layout attached as $ubi."
}

run_status() {
    local ibu_num ubi
    check_board
    check_geometry
    check_tools
    ibu_num="$(mtd_num ibu)" || die 'cannot resolve ibu MTD number'
    ubi="$(find_ubi_for_mtd "$ibu_num" 2>/dev/null || true)"
    if [ -z "$ubi" ]; then
        log 'Target UBI is not attached.'
        if has_ubi_header_near_start; then
            log 'UBI headers are present. Run: nokia-ubi-installer attach'
        else
            log 'Target still appears to contain the stock layout.'
        fi
        return 0
    fi
    if layout_complete "$ubi"; then
        log "[OK] $ubi has canonical IDs 0..5: ubootenv, ubootenv2, bosa, ri, fip, fit."
    else
        die "$ubi is attached but the canonical volume layout is incomplete"
    fi
}

run_install() {
    local requested="${1:-}" image ibu ibu_num ubi path id
    local fit_size installer_sha preloader_size fip_size preloader_sha fip_sha bosa_sha ri_sha bl2_ro
    local bl2_image_sha bl2_prefix_sha bl2_payload_sha payload_blocks

    image="$(resolve_sysupgrade "$requested" 2>/dev/null || true)"
    [ -z "$requested" ] || [ -n "$image" ] || die "cannot resolve requested OpenWrt sysupgrade image: $requested"
    base_check
    prepare_bl2_image
    [ -z "$image" ] || { [ "$(sha_file "$image")" = "$(expected_sysupgrade_sha)" ] || die 'selected UBI sysupgrade SHA256 mismatch'; check_sysupgrade "$image"; }

    if has_ubi_header_near_start; then
        log 'Existing UBI headers detected; refusing to format again automatically.'
        log 'Trying the non-destructive attach path instead.'
        attach_existing
        log 'Migration was already completed. Continue with nokia-ubi-finish and the UBI sysupgrade image.'
        return 0
    fi

    read_board_data
    capture_current_fit

    log ''
    log 'IRREVERSIBLE: stock NAND from 0x20000 will be formatted, then BL2, FIP and OpenWrt will be flashed.'
    log 'Continue only if a complete verified stock backup is saved on the PC, not only on the Nokia USB drive.'
    log 'Compatible NAND is mandatory; the blocked model remains unsupported.'
    [ "$(cat /tmp/NOKIA_NAND_IDENTITY 2>/dev/null || echo unknown)" != unknown ] || \
        log 'WARNING: NAND identity is unknown; exact geometry passed and compatibility remains the operator responsibility.'
    log 'Keep stable power. Do not reboot or disconnect power after authorization.'
    if [ "${NOKIA_PC_CONFIRMED_CUSTOM_FLASH:-0}" = 1 ]; then
        log 'PC WIZARD MODE: the selected image was validated and confirmed by the operator.'
        log 'Proceeding without another interactive prompt.'
    elif [ "${NOKIA_AUTOMATIC_FULLFLASH:-0}" = 1 ]; then
        log 'AUTOMATIC MODE: CONFIRM FORMAT AND FLASH was accepted before the transition bundle was written.'
        log 'Proceeding without another interactive prompt.'
    else
        printf 'Type exactly CONFIRM FORMAT AND FLASH: '
        IFS= read -r answer
        [ "$answer" = 'CONFIRM FORMAT AND FLASH' ] || die 'cancelled'
    fi
    touch /tmp/NOKIA_FORMAT_AND_FLASH_CONFIRMED
    touch /tmp/NOKIA_UBI_DESTRUCTIVE_STARTED
    ibu="$(mtd_dev ibu)" || critical 'ibu device disappeared'
    ibu_num="$(mtd_num ibu)" || critical 'cannot resolve ibu MTD number'

    log '[1/8] Formatting the all-in-UBI region.'
    for path in /sys/class/ubi/ubi[0-9]*; do
        [ -r "$path/mtd_num" ] || continue
        [ "$(cat "$path/mtd_num")" = "$ibu_num" ] || continue
        ubidetach -m "$ibu_num" || critical 'cannot detach target UBI device'
    done
    ubiformat -y "$ibu" || critical 'ubiformat failed'

    log '[2/8] Attaching UBI.'
    ubiattach -p "$ibu" || critical 'ubiattach failed'
    ubi="$(find_ubi_for_mtd "$ibu_num" 2>/dev/null || true)"
    [ -n "$ubi" ] || critical 'attached UBI device not found'
    ubi_mknod "$ubi" || critical "cannot create /dev/$ubi"

    log '[3/8] Creating canonical Nokia volumes with fixed IDs.'
    ubimkvol "/dev/$ubi" -n 0 -s 126976 -N ubootenv || critical 'cannot create ubootenv'
    ubimkvol "/dev/$ubi" -n 1 -s 126976 -N ubootenv2 || critical 'cannot create ubootenv2'
    ubimkvol "/dev/$ubi" -n 2 -s 262144 -N bosa || critical 'cannot create bosa'
    ubimkvol "/dev/$ubi" -n 3 -s 262144 -N ri || critical 'cannot create ri'
    ubimkvol "/dev/$ubi" -n 4 -t static -s 1048576 -N fip || critical 'cannot create fip'
    fit_size="$(file_size "$WORK/installer.itb")"
    ubimkvol "/dev/$ubi" -n 5 -s "$fit_size" -N fit || critical 'cannot create fit'
    id=0
    while [ "$id" -le 5 ]; do
        ubi_mknod "${ubi}_${id}" || critical "cannot create /dev/${ubi}_${id}"
        id=$((id + 1))
    done

    log '[4/8] Writing bosa and ri.'
    ubiupdatevol "/dev/${ubi}_2" "$WORK/bosa.bin" || critical 'cannot write bosa'
    ubiupdatevol "/dev/${ubi}_3" "$WORK/ri.bin" || critical 'cannot write ri'

    log '[5/8] Writing Ethernet-fixed FIP and fallback installer FIT.'
    ubiupdatevol "/dev/${ubi}_4" "$FIP" || critical 'cannot write FIP'
    ubiupdatevol "/dev/${ubi}_5" "$WORK/installer.itb" || critical 'cannot write fallback installer FIT'
    sync

    log '[6/8] Verifying all UBI payloads by readback SHA256.'
    bosa_sha="$(sha_file "$WORK/bosa.bin")"
    ri_sha="$(sha_file "$WORK/ri.bin")"
    fip_sha="$(sha_file "$FIP")"
    installer_sha="$(sha_file "$WORK/installer.itb")"
    fip_size="$(file_size "$FIP")"
    [ "$(readback_sha "/dev/${ubi}_2" 262144)" = "$bosa_sha" ] || critical 'bosa readback mismatch'
    [ "$(readback_sha "/dev/${ubi}_3" 262144)" = "$ri_sha" ] || critical 'ri readback mismatch'
    [ "$(readback_sha "/dev/${ubi}_4" "$fip_size")" = "$fip_sha" ] || critical 'FIP readback mismatch'
    [ "$(readback_sha "/dev/${ubi}_5" "$fit_size")" = "$installer_sha" ] || critical 'FIT readback mismatch'

    log '[7/8] Writing complete BL2 partition image last.'
    preloader_size="$(file_size "$PRELOADER")"
    preloader_sha="$(sha_file "$PRELOADER")"
    bl2_image_sha="$BL2_IMAGE_SHA"
    bl2_ro="$(mtd_ro bl2)" || critical 'BL2 read device is missing'

    mtd write "$BL2_IMAGE" bl2 || critical 'cannot erase/write complete BL2 partition image'
    sync

    [ "$(readback_sha "$bl2_ro" "$BL2_SIZE")" = "$bl2_image_sha" ] || \
        critical 'complete BL2 partition readback mismatch'
    bl2_prefix_sha="$(dd if="$bl2_ro" bs="$BL2_OFFSET" count=1 2>/dev/null | sha256sum | awk '{print $1}')"
    [ "$bl2_prefix_sha" = "$FF_2K_SHA" ] || critical 'BL2 readback prefix at 0x0..0x7ff is not all-FF'
    payload_blocks=$(( (preloader_size + BL2_OFFSET - 1) / BL2_OFFSET ))
    bl2_payload_sha="$(dd if="$bl2_ro" bs="$BL2_OFFSET" skip=1 count="$payload_blocks" 2>/dev/null | \
        head -c "$preloader_size" | sha256sum | awk '{print $1}')"
    [ "$bl2_payload_sha" = "$preloader_sha" ] || \
        critical 'BL2 raw preloader readback mismatch at physical offset 0x800'

    log '[8/8] Recording completion state.'
    printf '%s\n' "$ubi" > /tmp/NOKIA_UBI_DEVICE
    cat > /tmp/NOKIA_UBI_INSTALL_COMPLETE <<EOF
status=complete
ubi=$ubi
bosa_sha256=$bosa_sha
ri_sha256=$ri_sha
preloader_sha256=$preloader_sha
bl2_partition_sha256=$bl2_image_sha
bl2_preloader_offset=$BL2_OFFSET
fip_sha256=$fip_sha
installer_sha256=$installer_sha
EOF
    rm -f /tmp/NOKIA_UBI_INSTALL_FAILED
    sync

    log ''
    log 'UBI MIGRATION COMPLETE.'
    log 'Do not reboot manually yet. Install the production UBI image with:'
    log '  nokia-ubi-finish /path/to/openwrt-...-ubi-squashfs-sysupgrade.itb'
    log 'The fit volume currently contains this installer as a fallback.'
}

run_fullflash() {
    local image
    image="$(resolve_sysupgrade "${1:-}" 2>/dev/null || true)"
    [ -n "$image" ] || die "cannot resolve embedded OpenWrt sysupgrade or requested image path"
    [ -f "$image" ] || die "sysupgrade image not found: $image"
    [ "$(sha_file "$image")" = "$(expected_sysupgrade_sha)" ] || die 'selected UBI sysupgrade SHA256 mismatch'

    log "FULLFLASH image: $image"
    log 'FULLFLASH: check -> format stock NAND as all-in-UBI -> selected OpenWrt sysupgrade.'
    if [ "${NOKIA_PC_CONFIRMED_CUSTOM_FLASH:-0}" = 1 ]; then
        log 'PC wizard mode: the selected image was validated and confirmed after transition boot.'
    elif [ "${NOKIA_AUTOMATIC_FULLFLASH:-0}" = 1 ]; then
        log 'Automatic stage 2: authorization was already accepted on stock before reboot.'
    else
        log 'Nothing destructive happens before the single CONFIRM FORMAT AND FLASH confirmation.'
    fi
    run_install "$image" || return 1

    [ -f /tmp/NOKIA_UBI_INSTALL_COMPLETE ] || die 'migration completion marker is missing'
    log ''
    log 'Migration completed and verified. Starting production sysupgrade stage.'
    exec /usr/sbin/nokia-ubi-finish "$image"
}

usage() {
    cat <<'EOF'
Nokia XG-040G-MD installer RC28
Usage: nokia-ubi-installer check|install|fullflash|attach|status [IMAGE]
EOF
}

case "${1:-}" in
    check)
        shift
        run_check "$@"
        ;;
    install)
        shift
        [ "$#" -le 1 ] || { usage; exit 2; }
        run_install "$@"
        ;;
    fullflash)
        shift
        [ "$#" -le 1 ] || { usage; exit 2; }
        run_fullflash "${1:-}"
        ;;
    attach)
        base_check
        attach_existing
        ;;
    status)
        run_status
        ;;
    *)
        usage
        exit 2
        ;;
esac
                                                                                                                           































































































































































































































