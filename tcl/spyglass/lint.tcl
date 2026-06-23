# SpyGlass lint flow. Design engineers should maintain goals and methodology here.

set script_dir [file dirname [file normalize [info script]]]
source [file join $script_dir .. common run_de_common.tcl]
run_de::load_context
source [file join $script_dir common.tcl]

set lint_goals [list \
    lint/lint_rtl \
]

if {[catch {run_de_spyglass::run lint $lint_goals} run_error]} {
    puts stderr "run_de lint failed: $run_error"
    run_de::finish 1
    return -code error $run_error
}
run_de::finish 0
