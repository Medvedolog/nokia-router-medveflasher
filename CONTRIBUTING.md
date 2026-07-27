# Contributing

Changes to destructive flashing logic must be isolated in a separate commit
and accompanied by tests or a reproducible dry-run log. Never add vendor dumps,
private keys, device credentials, or OpenWrt firmware binaries to the repository.

Shell code must remain compatible with BusyBox `ash`. Host tools require
Python 3.10 or newer and use only the Python standard library.
