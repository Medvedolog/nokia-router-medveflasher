# RC23 timestamp + backup identity evidence

Release scope is PC-side orchestration and the live-stock backup agent only.

## Timestamp contract

`master.py` prefixes every non-empty operator line/prompt routed through the shared print/input layer with local `[YYYY-MM-DD HH:MM:SS]`. Blank separators remain blank. Input prompts get a PC-log-only newline after the answer.

## Backup identity contract

Direct TFTP and USB live-stock backups create `DEVICE_MAC.txt` containing `model`, `family`, local/UTC capture time, `primary_interface`, `primary_mac`, and discovered `interface_*` values. `eth0` is preferred. The file is created before `SHA256SUMS`, therefore it is integrity-covered. TFTP resume rejects a known different MAC in an existing destination. Legacy backups without the file remain accepted.

## Hardware status

The preceding RC22 MF install run completed transition `[1/8]..[8/8]` and verified production SSH + LuCI. RC23 timestamp/MAC additions themselves remain HW pending until exercised on-device.
