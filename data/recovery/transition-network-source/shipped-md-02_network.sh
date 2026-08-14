# MedveFlasher transition/recovery network policy: 2.5G is excluded; use LAN2-LAN4.
. /lib/functions/uci-defaults.sh
. /lib/functions/system.sh
an7581_setup_interfaces() {
	case "$1" in
	airoha,an7581-evb) ucidef_set_interfaces_lan_wan "lan2 lan3 lan4" "eth1" ;;
	gemtek,w1700k-ubi) ucidef_set_interfaces_lan_wan "lan2 lan3 lan4" "wan" ;;
	nokia,valyrian) ucidef_set_interfaces_lan_wan "lan2 lan3 10g" "wan" ;;
	nokia,xg-040g-md|nokia,xg-040g-md-ubi) ucidef_set_interface_lan "lan2 lan3 lan4" ;;
	*) echo "Unsupported hardware. Network interfaces not initialized" ;;
	esac
}
board_config_update
board=$(board_name)
an7581_setup_interfaces "$board"
board_config_flush
exit 0
