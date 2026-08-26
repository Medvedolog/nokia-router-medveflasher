# Source baseline for 1.0.0-rc35

This rollup was prepared from the public `Medvedolog/nokia-router-medveflasher` / uploaded source tree identifying itself as `1.0.0-rc33`, plus the behavior proven by the 2026-08-25 field log from a local `rc34` build. The local rc34 source archive was not supplied.

The rollup therefore explicitly incorporates the observed rc34 delta required to reach the failing path (removal of the stale RC32-prep1 MD stop), then applies the rc35 corrections: family-aware preflight error text, eraseblock-aligned MD auto bundle, and RI-derived device MAC identity.
