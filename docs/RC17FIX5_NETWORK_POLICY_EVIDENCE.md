# RC17fix5 transition/recovery network-script evidence

Exact fixed-size `/etc/board.d/02_network` entries extracted from the final MD/MF transition initramfs.

- MD: `767` bytes, SHA256 `10244ac23e2a7baa3faafa80da134e85324baf80486b871d73240c178c5247a4`
- MF: `591` bytes, SHA256 `af0757d1968f3c1ded7cf4fcb532871fa3562b582072fa5505d59b84f7188a3b`
- ASCII only: PASS
- literal `lan1`: absent in both: PASS
- Nokia stable bridge members: `lan2 lan3 lan4`: PASS

The build-time patcher source is `data/recovery/transition-network-source/patch_transition_network.py`.
