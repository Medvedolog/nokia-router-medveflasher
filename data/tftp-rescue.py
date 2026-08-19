#!/usr/bin/env python3
"""Serve the rescue image to a device already asking for it.

When a production boot fails, the installed OpenWrt U-Boot does not stop: its
default environment runs

    boot_ubi          = run boot_production ; run boot_tftp_forever
    boot_tftp_forever = led $bootled_status on ; while true ; do run boot_tftp ; sleep 1 ; done
    boot_tftp         = tftpboot $loadaddr $bootfile && bootm $loadaddr#$bootconf

so the board loops forever requesting $bootfile from $serverip. Holding Reset
reaches the same place through check_buttons. Nothing on the PC was answering
that request, which is why an interrupted sysupgrade looked like a brick.

A board only gets that far when BL2 and the FIP are already written, so the
migration ran. The default answer is therefore the transition system: it is the
only image in the kit carrying nokia-ubi-installer and nokia-ubi-finish, and its
installer detects existing UBI headers, refuses to format again and takes the
non-destructive attach path -- so the install can be finished rather than
repeated. Pass --stock-recovery for the stock rollback vehicle instead.
"""
import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import master  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=("md", "mf"), default="md")
    parser.add_argument("--local-ip", default="192.168.1.254",
                        help="this PC; must match U-Boot's serverip")
    parser.add_argument("--router-ip", default="192.168.1.1")
    parser.add_argument("--stock-recovery", action="store_true",
                        help="serve the stock rollback initramfs instead of the "
                             "transition system that can finish an install")
    parser.add_argument("--image", type=Path, default=None,
                        help="override the image to serve")
    parser.add_argument("--name", default=None,
                        help="override the filename U-Boot requests")
    parser.add_argument("--attempts", type=int, default=40)
    args = parser.parse_args()

    board = "nokia,xg-040g-mf-ubi" if args.family == "mf" else "nokia,xg-040g-md-ubi"
    image, name = master._rescue_tftp_for_board(board, stock_recovery=args.stock_recovery)
    if args.image:
        image = master._fit_only(args.image)
    if args.name:
        name = args.name

    if not image.is_file():
        print(f"[ERROR] image not found: {image}")
        return 2

    role = "stock rollback" if args.stock_recovery else "transition (can finish the install)"
    print(f"[TFTP] serving {image.name} ({image.stat().st_size / 1048576:.1f} MiB) - {role}")
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
            print(f"[OK] delivered {result.bytes_transferred} bytes; the board is booting it.")
            print(f"[NEXT] Wait ~60s, then reach it over SSH at {args.router_ip}.")
            if not args.stock_recovery:
                print("[NEXT] Then run the wizard's installation-continuation entry: the "
                      "installer sees the existing UBI, skips the format and finishes the "
                      "production write.")
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
