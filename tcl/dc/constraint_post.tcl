# Design Compiler post-SDC constraint hook.
#
# This file is sourced after the design SDC and before SDC sanity reports.
# Keep this file empty for the default flow. Put project-specific constraint
# tweaks here when needed, for example early QoR clock uncertainty, extra clock
# groups, false paths, or IO constraint supplements.
#
# Example: conservative setup uncertainty for early synthesis exploration.
# Uncomment and tune only when the project wants this behavior.
#
# foreach_in_collection clk [all_clocks] {
#     set clk_prd [get_attribute [get_clocks $clk] period]
#     set clk_uncer [expr 0.25 * $clk_prd]
#     if {$clk_uncer >= 1.0} {
#         set clk_uncer 1.0
#     }
#     set_clock_uncertainty $clk_uncer -setup [get_clocks $clk]
# }
update_timing

foreach_in_collection clk [all_clocks] {
    set clk_name [get_object_name $clk]
    set clk_prd [get_attribute $clk period]

    if {![string is double -strict $clk_prd]} {
        error "Clock '$clk_name' has no valid period; check its clock definition."
    }

    set clk_uncer [expr {min(0.25 * $clk_prd, 1.0)}]
    set_clock_uncertainty -setup $clk_uncer $clk
}
