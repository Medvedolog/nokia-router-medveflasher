from __future__ import annotations

import struct
import unittest
import zlib

from tools.prepare_env import (
    BOOTLOADER_SIZE,
    DEFAULT_BOOTCMD,
    ENV_BLOCK_OFFSET,
    ENV_BLOCK_SIZE,
    ENV_PARTITION_OFFSET,
    ENV_PARTITION_SIZE,
    EnvError,
    build_env_block,
    build_partition,
    parse_env_block,
)


class PrepareEnvTests(unittest.TestCase):
    def synthetic_bootloader(self) -> bytes:
        entries = [
            ("bootdelay", "3"),
            ("ethaddr", "00:11:22:33:44:55"),
            ("bootcmd", "run vendor_boot"),
        ]
        env = build_env_block(entries)
        partition = bytearray(b"\xff" * ENV_PARTITION_SIZE)
        partition[ENV_BLOCK_OFFSET : ENV_BLOCK_OFFSET + ENV_BLOCK_SIZE] = env
        bootloader = bytearray(b"\xff" * BOOTLOADER_SIZE)
        bootloader[
            ENV_PARTITION_OFFSET : ENV_PARTITION_OFFSET + ENV_PARTITION_SIZE
        ] = partition
        return bytes(bootloader)

    def test_updates_only_bootcmd_and_crc(self) -> None:
        source = self.synthetic_bootloader()
        output, report = build_partition(source, DEFAULT_BOOTCMD)
        self.assertEqual(len(output), ENV_PARTITION_SIZE)
        block = output[ENV_BLOCK_OFFSET : ENV_BLOCK_OFFSET + ENV_BLOCK_SIZE]
        entries = dict(parse_env_block(block))
        self.assertEqual(entries["ethaddr"], "00:11:22:33:44:55")
        self.assertEqual(entries["bootcmd"], DEFAULT_BOOTCMD)
        stored = struct.unpack_from("<I", block, 0)[0]
        self.assertEqual(stored, zlib.crc32(block[4:]) & 0xFFFFFFFF)
        self.assertEqual(report["old_bootcmd"], "run vendor_boot")

    def test_rejects_bad_crc(self) -> None:
        source = bytearray(self.synthetic_bootloader())
        source[ENV_PARTITION_OFFSET + ENV_BLOCK_OFFSET] ^= 0x01
        with self.assertRaises(EnvError):
            build_partition(bytes(source), DEFAULT_BOOTCMD)

    def test_rejects_wrong_input_size(self) -> None:
        with self.assertRaises(EnvError):
            build_partition(b"x" * 1234, DEFAULT_BOOTCMD)


if __name__ == "__main__":
    unittest.main()
