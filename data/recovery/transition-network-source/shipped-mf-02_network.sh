# MedveFlasher transition/recovery network policy: 2.5G is excluded; use LAN2-LAN4.
. /lib/functions/uci-defaults.sh
. /lib/functions/system.sh
an7583_setup_interfaces() {
	case "$1" in
	airoha,an7583-evb) ucidef_set_interface_lan "lan2 lan3 lan4 eth1" ;;
	nokia,xg-040g-mf|nokia,xg-040g-mf-ubi) ucidef_set_interface_lan "lan2 lan3 lan4" ;;
	*) echo "Unsupported hardware. Network interfaces not initialized" ;;
	esac
}
board_config_update
board=$(board_name)
an7583_setup_interfaces "$board"
board_config_flush
exit 0
