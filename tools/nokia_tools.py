#!/usr/bin/env python3
"""Unified host utility for preparing a Nokia XG-040G-MD installation bundle."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import prepare_bundle, prepare_env, verify_backup  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify-backup", help="verify a full stock backup")
    verify.add_argument("backup_dir", type=Path)

    env = sub.add_parser("prepare-env", help="generate personalized U-Boot env")
    env.add_argument("--input", required=True, type=Path)
    env.add_argument("--output", required=True, type=Path)
    env.add_argument("--report-json", type=Path)
    env.add_argument("--force", action="store_true")

    bundle = sub.add_parser("prepare-bundle", help="create a validated USB bundle")
    bundle.add_argument("--kernel", required=True, type=Path)
    bundle.add_argument("--rootfs", required=True, type=Path)
    bundle.add_argument("--env", required=True, type=Path)
    bundle.add_argument("--sha256sums", required=True, type=Path)
    bundle.add_argument("--output", required=True, type=Path)
    bundle.add_argument("--router-dir", type=Path)
    bundle.add_argument("--confirm-skyhigh", action="store_true")
    bundle.add_argument("--force", action="store_true")

    all_in_one = sub.add_parser(
        "prepare-usb", help="verify backup, generate env and create the final USB bundle"
    )
    all_in_one.add_argument("--backup", required=True, type=Path)
    all_in_one.add_argument("--kernel", required=True, type=Path)
    all_in_one.add_argument("--rootfs", required=True, type=Path)
    all_in_one.add_argument("--sha256sums", required=True, type=Path)
    all_in_one.add_argument("--output", required=True, type=Path)
    all_in_one.add_argument("--router-dir", type=Path)
    all_in_one.add_argument("--confirm-skyhigh", action="store_true")
    all_in_one.add_argument("--force", action="store_true")

    return parser


def run_prepare_usb(args: argparse.Namespace) -> int:
    try:
        verify_backup.verify_backup_directory(args.backup)
        with tempfile.TemporaryDirectory(prefix="nokia-xg040gmd-") as temp_dir:
            env_path = Path(temp_dir) / "OpenWrt.mtd2.u-boot-env.bin"
            report_path = Path(temp_dir) / "env-report.json"
            prepare_env.generate_env_image(
                args.backup / "mtd0_bootloader.bin.gz",
                env_path,
                report_json=report_path,
            )
            prepare_bundle.create_bundle(
                kernel=args.kernel,
                rootfs=args.rootfs,
                env=env_path,
                openwrt_sha256sums=args.sha256sums,
                output=args.output,
                router_dir=args.router_dir,
                confirm_skyhigh=args.confirm_skyhigh,
                force=args.force,
            )
    except (
        OSError,
        prepare_env.EnvError,
        prepare_bundle.BundleError,
        verify_backup.BackupError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Final USB bundle created at: {args.output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)

    if args.command == "verify-backup":
        return verify_backup.main([str(args.backup_dir)])
    if args.command == "prepare-env":
        command = ["--input", str(args.input), "--output", str(args.output)]
        if args.report_json:
            command += ["--report-json", str(args.report_json)]
        if args.force:
            command.append("--force")
        return prepare_env.main(command)
    if args.command == "prepare-bundle":
        command = [
            "--kernel",
            str(args.kernel),
            "--rootfs",
            str(args.rootfs),
            "--env",
            str(args.env),
            "--sha256sums",
            str(args.sha256sums),
            "--output",
            str(args.output),
        ]
        if args.router_dir:
            command += ["--router-dir", str(args.router_dir)]
        if args.confirm_skyhigh:
            command.append("--confirm-skyhigh")
        if args.force:
            command.append("--force")
        return prepare_bundle.main(command)
    if args.command == "prepare-usb":
        return run_prepare_usb(args)

    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
