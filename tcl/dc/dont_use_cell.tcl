# Design Compiler dont-use library cell rules.
#
# This file is sourced after target/link library setup and before RTL analysis.
# Keep project/process-specific forbidden cells here so synthesis will avoid
# mapping to them.

set_dont_use [get_lib_cells "*/*ULVT*"]
set_dont_use [get_lib_cells "*/*DO*"]
set_dont_use [get_lib_cells "*/*BUFFD1BWP*"]
set_dont_use [get_lib_cells "*/*BUFFD20BWP*"]
set_dont_use [get_lib_cells "*/*INVD1BWP*"]
set_dont_use [get_lib_cells "*/*INVD20BWP*"]
set_dont_use [get_lib_cells "*/*DEL*"]
set_dont_use [get_lib_cells "*/*CK*"]
set_dont_use [get_lib_cells "*/*TIE*"]

# Optional, enable only if the project wants to avoid these arithmetic cells.
# set_dont_use [get_lib_cells "*/*FA*"]
# set_dont_use [get_lib_cells "*/*HA*"]
