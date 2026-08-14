#!/bin/ash
mkdir -p /www
{ echo MEDVEFLASHER_TRANSITION_PROTOCOL=1; echo MODE=TRANSITION; echo FAMILY=MF; echo STATE=BOOTING; echo SAFE_TO_POWER_CYCLE=1; } >/www/medveflasher-transition.status
exit 0
