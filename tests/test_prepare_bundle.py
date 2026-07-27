from __future__ import annotations

import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from tools.prepare_bundle import BundleError, create_bundle
from tools.prepare_env import DEFAULT_BOOTCMD, ENV_BLOCK_OFFSET, ENV_BLOCK_SIZE, ENV_PARTITION_SIZE, build_env_block


class PrepareBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.kernel = self.root / "openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-kernel.bin"
        self.rootfs = self.root / "openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-rootfs.bin"
        self.env = self.root / "OpenWrt.mtd2.u-boot-env.bin"
        self.sums = self.root / "sha256sums"
        self.router = self.root / "router"
        self.output = self.root / "bundle"

        self.kernel.write_bytes(struct.pack(">I", 0xD00DFEED) + b"kernel")
        self.rootfs.write_bytes(b"UBI#" + b"rootfs")
        partition = bytearray(b"\xff" * ENV_PARTITION_SIZE)
        block = build_env_block([("bootcmd", DEFAULT_BOOTCMD), ("ethaddr", "00:11:22:33:44:55")])
        partition[ENV_BLOCK_OFFSET : ENV_BLOCK_OFFSET + ENV_BLOCK_SIZE] = block
        self.env.write_bytes(partition)

        self.sums.write_text(
            f"{hashlib.sha256(self.kernel.read_bytes()).hexdigest()}  {self.kernel.name}\n"
            f"{hashlib.sha256(self.rootfs.read_bytes()).hexdigest()}  {self.rootfs.name}\n",
            encoding="ascii",
        )
        self.router.mkdir()
        for name in ("lib.sh", "preflight.sh", "flash-stock-layout.sh"):
            (self.router / name).write_bytes(b"#!/bin/ash\r\necho ok\r\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_creates_bundle_and_normalizes_shell_lf(self) -> None:
        create_bundle(
            kernel=self.kernel,
            rootfs=self.rootfs,
            env=self.env,
            openwrt_sha256sums=self.sums,
            output=self.output,
            router_dir=self.router,
            confirm_skyhigh=True,
        )
        self.assertTrue((self.output / "SHA256SUMS").is_file())
        self.assertNotIn(b"\r", (self.output / "preflight.sh").read_bytes())
        manifest = (self.output / "SHA256SUMS").read_text(encoding="ascii")
        self.assertIn("BUNDLE_INFO.txt", manifest)
        self.assertIn("OPENWRT_SHA256SUMS.txt", manifest)

    def test_rejects_unlisted_openwrt_image(self) -> None:
        self.sums.write_text("0" * 64 + "  unrelated.bin\n", encoding="ascii")
        with self.assertRaises(BundleError):
            create_bundle(
                kernel=self.kernel,
                rootfs=self.rootfs,
                env=self.env,
                openwrt_sha256sums=self.sums,
                output=self.output,
                router_dir=self.router,
                confirm_skyhigh=True,
            )

    def test_requires_skyhigh_confirmation(self) -> None:
        with self.assertRaises(BundleError):
            create_bundle(
                kernel=self.kernel,
                rootfs=self.rootfs,
                env=self.env,
                openwrt_sha256sums=self.sums,
                output=self.output,
                router_dir=self.router,
            )


if __name__ == "__main__":
    unittest.main()
