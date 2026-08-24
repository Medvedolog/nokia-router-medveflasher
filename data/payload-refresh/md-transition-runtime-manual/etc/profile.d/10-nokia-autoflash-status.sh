#!/bin/ash
[ -f /tmp/NOKIA_MANUAL_TRANSITION_READY ] || return 0
echo
echo '=== Nokia Router MedveFlasher manual transition ==='
echo 'State: waiting for the PC wizard to upload and validate a sysupgrade image.'
echo 'No automatic NAND formatting is scheduled.'
echo
