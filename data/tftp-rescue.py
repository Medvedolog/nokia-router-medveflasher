#!/usr/bin/env python3
"""Serve the recovery initramfs to a device already asking for it.

When a production boot fails, the installed OpenWrt U-Boot does not stop: its
default environment runs

    boot_ubi          = run boot_production ; run boot_tftp_forever
    boot_tftp_forever = led $bootled_status on ; while true ; do run boot_tftp ; sleep 1 ; done
    boot_tftp         = tftpboot $loadaddr $bootfile && bootm $loadaddr#$bootconf

so the board loops forever requesting $bootfile from $serverip. Holding Reset
reaches the same place through check_buttons. Nothing on the PC was answering
that request, which is why an interrupted sysupgrade looked like a brick.

This serves the kit's recovery image under the name U-Boot asks for, and keeps
serving until the transfer completes. No SSH, no UART, no stock system needed.
"""
import argparse
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import master  # noqa: E402



def _fit_only(image: Path) -> Path:
    """Serve exactly the flattened image, never the bytes appended after it."""
    head = image.read_bytes()[:40]
    if len(head) < 8 or int.from_bytes(head[:4], "big") != 0xD00DFEED:
        print(f"[WARN] {image.name} is not a flattened image; serving it verbatim.")
        return image
    total = int.from_bytes(head[4:8], "big")
    actual = image.stat().st_size
    if total >= actual:
        return image
    trimmed = Path(tempfile.gettempdir()) / f"medveflasher-fit-{image.stem}.itb"
    trimmed.write_bytes(image.read_bytes()[:total])
    print(f"[TFTP] {image.name}: serving the leading {total} bytes of FIT "
          f"({actual - total} appended bytes withheld)")
    return trimmed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=("md", "mf"), default="md")
    parser.add_argument("--local-ip", default="192.168.1.254",
                        help="this PC; must match U-Boot's serverip")
    parser.add_argument("--router-ip", default="192.168.1.1")
    parser.add_argument("--image", type=Path, default=None,
                        help="override the recovery .itb to serve")
    parser.add_argument("--name", default=None,
                        help="override the filename U-Boot requests")
    parser.add_argument("--attempts", type=int, default=40)
    args = parser.parse_args()

    if args.family == "md":
        image = args.image or master.RECOVERY_INITRAMFS
        name = args.name or master.UBOOT_DEFAULT_RECOVERY_FILENAME
    else:
        image = args.image or master.MF_STOCK_RECOVERY_INITRAMFS
        name = args.name or master.UBOOT_DEFAULT_RECOVERY_FILENAME.replace(
            "an7581", "an7583").replace("xg-040g-md", "xg-040g-mf")

    if not image.is_file():
        print(f"[ERROR] recovery image not found: {image}")
        return 2

    # transition-bundle.bin is a FIT with the production sysupgrade appended, so
    # the file on disk is far larger than the image U-Boot should receive. Serve
    # exactly the FIT and nothing after it.
    image = _fit_only(image)

    print(f"[TFTP] serving {image.name} ({image.stat().st_size / 1048576:.1f} MiB)")
    print(f"[TFTP] as '{name}' on {args.local_ip}:69, for {args.router_ip}")
    print("[TFTP] Cable in LAN2/LAN3/LAN4 - U-Boot's Ethernet is not on the 2.5G port.")
    print("[TFTP] Power the router on now, or hold Reset while powering on.")

    for attempt in range(1, args.attempts + 1):
        ready = threading.Event()
        result = master.TftpResult()
        thread = threading.Thread(
            target=master.serve_tftp_get,
            args=(args.local_ip, 69, image, name, args.router_ip, ready, result),
            kwargs={"timeout": 60, "maximum_block_size": 1468},
            daemon=True,
        )
        thread.start()
        if not ready.wait(10):
            print("[ERROR] could not bind UDP/69 - run as Administrator/sudo, "
                  "and check that no other TFTP server holds the port.")
            return 2
        thread.join()
        if result.bytes_transferred > 0 and not result.error:
            print(f"[OK] delivered {result.bytes_transferred} bytes; "
                  "the board is booting the recovery image.")
            print("[NEXT] Wait ~60s, then reach it over SSH at "
                  f"{args.router_ip} and re-run the production sysupgrade.")
            return 0
        detail = f": {result.error}" if result.error else ""
        print(f"[WAIT] attempt {attempt}/{args.attempts} - no request yet{detail}")
        time.sleep(1)

    print("[ERROR] the board never asked for the file.")
    print("        Check the cable is in LAN2-4, the PC really holds "
          f"{args.local_ip}/24, and that Wi-Fi/VPN are off.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
