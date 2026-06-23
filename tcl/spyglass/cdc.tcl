# SpyGlass CDC flow. Design engineers should maintain goals and methodology here.

set script_dir [file dirname [file normalize [info script]]]
source [file join $script_dir .. common run_de_common.tcl]
run_de::load_context
source [file join $script_dir common.tcl]

set cdc_goals [list \
    cdc/cdc_setup_check \
    cdc/clock_reset_integrity \
    cdc/cdc_verify_struct \
    cdc/cdc_verify \
]

if {[catch {run_de_spyglass::run cdc $cdc_goals} run_error]} {
    puts stderr "run_de CDC failed: $run_error"
    run_de::finish 1
    return -code error $run_error
}
run_de::finish 0
