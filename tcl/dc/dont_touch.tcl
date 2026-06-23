# Design Compiler dont-touch hook.
#
# This file is sourced after uniquify and before the uniquified GTECH snapshot
# is written. Keep it empty for the default flow. Add project-specific
# protection here when needed.
#
# Common examples:
#
# set_dont_touch [get_cells -hierarchical "*u_sram*"]
# set_dont_touch [get_designs "analog_macro"]
# set_dont_touch_network [get_ports "scan_enable"]
#
# Be conservative: dont-touch constraints can significantly affect QoR if they
# protect logic that DC should optimize.
