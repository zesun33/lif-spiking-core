read_lef /opt/platforms/nangate45/NangateOpenCellLibrary.tech.lef
read_lef /opt/platforms/nangate45/NangateOpenCellLibrary.macro.lef
read_liberty /opt/platforms/nangate45/NangateOpenCellLibrary_typical.lib

read_verilog lif_mesh_2x2.gate.v
link_design lif_mesh_2x2

current_design lif_mesh_2x2
create_clock -name clk -period 10.0 [get_ports clk]
set_input_delay -clock clk 1.0 [all_inputs]
set_output_delay -clock clk 1.0 [all_outputs]

# 65% utilization (compact die)
initialize_floorplan -site FreePDK45_38x28_10R_NP_162NW_34O -utilization 65 -aspect_ratio 1.0 -core_space 15.0
make_tracks
place_pins -hor_layer metal3 -ver_layer metal2

global_placement -density 0.70
estimate_parasitics -placement
repair_design
repair_timing -setup
detailed_placement
global_route

save_image -area {0 0 320 320} -width 1200 lif_mesh_2x2_compact.png
puts "SAVED_COMPACT_IMAGE"
exit
