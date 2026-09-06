# run_mesh_pnr.tcl — OpenROAD Physical Design Script for 4-Core 2x2 LIF Neuromorphic Mesh SoC
read_lef /opt/platforms/nangate45/NangateOpenCellLibrary.tech.lef
read_lef /opt/platforms/nangate45/NangateOpenCellLibrary.macro.lef
read_liberty /opt/platforms/nangate45/NangateOpenCellLibrary_typical.lib

read_verilog lif_mesh_2x2.gate.v
link_design lif_mesh_2x2

# 100 MHz target clock (10.0 ns period)
current_design lif_mesh_2x2
create_clock -name clk -period 10.0 [get_ports clk]
set_input_delay -clock clk 1.0 [all_inputs]
set_output_delay -clock clk 1.0 [all_outputs]

# Floorplanning: 45% core density, 15um core margin
initialize_floorplan -site FreePDK45_38x28_10R_NP_162NW_34O -utilization 45 -aspect_ratio 1.0 -core_space 15.0
make_tracks
place_pins -hor_layer metal3 -ver_layer metal2

# Placement & High-Fanout Buffer Insertion / Timing Repair
global_placement -density 0.50
estimate_parasitics -placement
repair_design
repair_timing -setup
detailed_placement

# Routing
global_route

# Timing & Parasitic Extraction
estimate_parasitics -placement
report_checks -path_delay max
report_wns
report_tns
report_worst_slack -max

# Export Tapeout DEF
write_def lif_mesh_2x2.routed.def
puts "PHYSICAL_DESIGN_SUCCESS"
exit
