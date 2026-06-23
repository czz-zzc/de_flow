# Design Compiler synthesis flow.
# Project-specific library setup can be added above analyze/elaborate below.

set script_dir [file dirname [file normalize [info script]]]
source [file join $script_dir .. common run_de_common.tcl]
source [file join $script_dir report_sdc_check.tcl]
source [file join $script_dir report_final.tcl]
run_de::load_context

puts "Starting synthesis for $run_de(design)"
set PRJ_CODE $env(PRJ_CODE)
set_svf [file join $run_de(output_dir) "$run_de(design)_syn.svf"]

# Use more workers in topographical mode while keeping a conservative default
# for wire-load mode. Adjust these values for the available host/license pool.
if {[shell_is_in_topographical_mode]} {
    set_host_options -max_cores 4
} else {
    set_host_options -max_cores 2
}

# Keep generated bus and multi-dimensional names stable for downstream P&R,
# netlist processing, and Formality scripts.
set_app_var bus_range_separator_style "_TO_"
set_app_var bus_multiple_separator_style "_AND_"
set_app_var bus_multiple_name_separator_style "_MB_"
set_app_var verilogout_no_tri true

# DesignWare is part of the synthetic library. Target/link technology DB files
# are supplied by common_db.yaml through run_de(library_files).
set_app_var synthetic_library "dw_foundation.sldb"
if {[llength $run_de(library_files)] > 0} {
    set_app_var target_library $run_de(library_files)
    set_app_var link_library \
        [concat "*" $run_de(library_files) $synthetic_library]
} else {
    set_app_var link_library [list "*" $synthetic_library]
}

run_de::optional_source $run_de(dont_use_cell_tcl) "dont-use cell Tcl"

set design_lib_dir [file join $run_de(work_dir) work WORK]
file mkdir $design_lib_dir
define_design_lib WORK -path $design_lib_dir

set syn_define_options ""
foreach define $run_de(defines) {
    append syn_define_options " +define+$define"
}

foreach filelist $run_de(filelists) {
    analyze -format sverilog -vcs "-f $filelist $syn_define_options"
}
elaborate $run_de(design)
current_design $run_de(design)

if {[link]} {
    puts "ELAB END: link completed successfully."
} else {
    puts stderr "Error: ELAB ABORT: link failed for $run_de(design)"
    exit 1
}

# Normalize names before writing Verilog so the GTECH and mapped netlists use
# legal, stable Verilog identifiers for downstream tools.
change_names -rules verilog -hierarchy -verbose

# Save the linked, pre-compile GTECH view for debug/Formality bring-up.
# These files capture the elaborated design before mapping/optimization.
write -format verilog -hierarchy \
    -output [file join $run_de(output_dir) "$run_de(design)_gtech.v"]
write -format ddc -hierarchy \
    -output [file join $run_de(output_dir) "$run_de(design)_gtech.ddc"]

# Uniquify after saving the original linked GTECH snapshot, then save a second
# GTECH snapshot so hierarchy/name changes can be reviewed explicitly.
set_app_var uniquify_naming_style "${run_de(design)}_%s_%d"
uniquify -force
run_de::optional_source $run_de(dont_touch_tcl) "dont touch Tcl"
# set_fix_multiple_port_nets -all -buffer_constants [all_designs]
# change_names -rules verilog -hierarchy -verbose

write -format verilog -hierarchy \
    -output [file join $run_de(output_dir) "$run_de(design)_gtech_uniq.v"]
write -format ddc -hierarchy \
    -output [file join $run_de(output_dir) "$run_de(design)_gtech_uniq.ddc"]

if {$run_de(sdc_file) ne ""} {
    source -echo -verbose $run_de(sdc_file)
    run_de::optional_source $run_de(constraint_post_tcl) "constraint post Tcl"
    run_de::dc_report_sdc_check
}

# Default compile constraints. These are intentionally placed after SDC loading
# so they apply to the final constraint state used by compile_ultra.
set_max_area 0
set_max_fanout 32 [current_design]
set_max_fanout 32 [get_designs *]
set_register_merging [get_designs *] false
set_leakage_optimization true

#set_cost_priority -delay
#set compile_timing_high_effort true


#compile_ultra -scan -timing_high_effort_script -gate_clock -no_autoungroup -no_seq_output_inversion -no_boundary_optimization
compile_ultra  -gate_clock -no_autoungroup -no_seq_output_inversion -no_boundary_optimization

change_names -rules verilog -hierarchy -verbose
run_de::dc_report_final

write -format verilog -hierarchy \
    -output [file join $run_de(output_dir) "$run_de(design)_syn.v"]
write -format ddc -hierarchy \
    -output [file join $run_de(output_dir) "$run_de(design)_syn.ddc"]
write_sdc [file join $run_de(output_dir) "$run_de(design)_syn.sdc"]
set_svf -off

puts "Synthesis completed for $run_de(design)"
