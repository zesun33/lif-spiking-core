// =============================================================================
// Module: lif_mesh_2x2
// Description: 4-Core 2D Neuromorphic Mesh SoC Network.
//              Integrates four 8x8 LIF Spiking Core Tiles with five-port AER
//              routers in a 2x2 grid with Dimension-Order Routing (X-then-Y).
//
// Topology:
//    [ Node (0, 0) ] <====== East/West ======> [ Node (1, 0) ]
//          ||                                        ||
//      North/South                               North/South
//          ||                                        ||
//    [ Node (0, 1) ] <====== East/West ======> [ Node (1, 1) ]
// =============================================================================

`timescale 1ns / 1ps

module lif_mesh_2x2 #(
    parameter WEIGHT_WIDTH = 8,
    parameter MEM_WIDTH    = 16,
    parameter PACKET_WIDTH = 16
)(
    input  wire                               clk,
    input  wire                               rst_n,

    // Global Timestep Synchronization
    input  wire                               timestep_tick,

    // Memory-Mapped Synaptic Configuration Demux
    input  wire [1:0]                         cfg_node_sel, // 00:(0,0), 01:(1,0), 10:(0,1), 11:(1,1)
    input  wire                               cfg_we,
    input  wire [5:0]                         cfg_addr,
    input  wire signed [WEIGHT_WIDTH-1:0]     cfg_wdata,
    output reg  signed [WEIGHT_WIDTH-1:0]     cfg_rdata,

    // Global Hyperparameters
    input  wire signed [MEM_WIDTH-1:0]        v_threshold,
    input  wire signed [MEM_WIDTH-1:0]        v_rest,

    // Static Routing Tables per Tile (8 neurons * 9 bits = 72 bits each)
    input  wire [71:0]                        routing_table_00,
    input  wire [71:0]                        routing_table_10,
    input  wire [71:0]                        routing_table_01,
    input  wire [71:0]                        routing_table_11,

    // Core Egress Spike Observability Buses
    output wire [7:0]                         node00_spikes,
    output wire [7:0]                         node10_spikes,
    output wire [7:0]                         node01_spikes,
    output wire [7:0]                         node11_spikes,

    // Core Refractory Status Buses
    output wire [7:0]                         node00_refractory,
    output wire [7:0]                         node10_refractory,
    output wire [7:0]                         node01_refractory,
    output wire [7:0]                         node11_refractory
);

    // =========================================================================
    // 1. Configuration Readback Demux
    // =========================================================================
    wire signed [WEIGHT_WIDTH-1:0] rdata_00, rdata_10, rdata_01, rdata_11;

    always @(*) begin
        case (cfg_node_sel)
            2'b00: cfg_rdata = rdata_00;
            2'b01: cfg_rdata = rdata_10;
            2'b10: cfg_rdata = rdata_01;
            2'b11: cfg_rdata = rdata_11;
            default: cfg_rdata = {WEIGHT_WIDTH{1'b0}};
        endcase
    end

    // =========================================================================
    // 2. Inter-Node 2D Mesh Network Wires
    // =========================================================================
    // Horizontal Link: (0,0) East <-> (1,0) West
    wire                    net_00_to_10_valid;
    wire [PACKET_WIDTH-1:0] net_00_to_10_packet;
    wire                    net_00_to_10_ready;

    wire                    net_10_to_00_valid;
    wire [PACKET_WIDTH-1:0] net_10_to_00_packet;
    wire                    net_10_to_00_ready;

    // Horizontal Link: (0,1) East <-> (1,1) West
    wire                    net_01_to_11_valid;
    wire [PACKET_WIDTH-1:0] net_01_to_11_packet;
    wire                    net_01_to_11_ready;

    wire                    net_11_to_01_valid;
    wire [PACKET_WIDTH-1:0] net_11_to_01_packet;
    wire                    net_11_to_01_ready;

    // Vertical Link: (0,0) South <-> (0,1) North
    wire                    net_00_to_01_valid;
    wire [PACKET_WIDTH-1:0] net_00_to_01_packet;
    wire                    net_00_to_01_ready;

    wire                    net_01_to_00_valid;
    wire [PACKET_WIDTH-1:0] net_01_to_00_packet;
    wire                    net_01_to_00_ready;

    // Vertical Link: (1,0) South <-> (1,1) North
    wire                    net_10_to_11_valid;
    wire [PACKET_WIDTH-1:0] net_10_to_11_packet;
    wire                    net_10_to_11_ready;

    wire                    net_11_to_10_valid;
    wire [PACKET_WIDTH-1:0] net_11_to_10_packet;
    wire                    net_11_to_10_ready;

    // =========================================================================
    // 3. Instantiate Node (0, 0) — Top-Left
    // =========================================================================
    lif_mesh_node_2d #(
        .TILE_X       (0),
        .TILE_Y       (0),
        .COORD_WIDTH  (3),
        .AXON_WIDTH   (3),
        .PACKET_WIDTH (PACKET_WIDTH),
        .WEIGHT_WIDTH (WEIGHT_WIDTH),
        .MEM_WIDTH    (MEM_WIDTH)
    ) u_node_00 (
        .clk                 (clk),
        .rst_n               (rst_n),
        .timestep_tick       (timestep_tick),
        .cfg_we              (cfg_we && (cfg_node_sel == 2'b00)),
        .cfg_addr            (cfg_addr),
        .cfg_wdata           (cfg_wdata),
        .cfg_rdata           (rdata_00),
        .v_threshold         (v_threshold),
        .v_rest              (v_rest),
        .routing_table       (routing_table_00),
        .tile_spikes_out     (node00_spikes),
        .tile_refractory_bus (node00_refractory),

        // North: Perimeter Edge
        .north_in_valid      (1'b0),
        .north_in_packet     ({PACKET_WIDTH{1'b0}}),
        .north_in_ready      (),
        .north_out_valid     (),
        .north_out_packet    (),
        .north_out_ready     (1'b1),

        // South: Connected to Node (0, 1)
        .south_in_valid      (net_01_to_00_valid),
        .south_in_packet     (net_01_to_00_packet),
        .south_in_ready      (net_01_to_00_ready),
        .south_out_valid     (net_00_to_01_valid),
        .south_out_packet    (net_00_to_01_packet),
        .south_out_ready     (net_00_to_01_ready),

        // East: Connected to Node (1, 0)
        .east_in_valid       (net_10_to_00_valid),
        .east_in_packet      (net_10_to_00_packet),
        .east_in_ready       (net_10_to_00_ready),
        .east_out_valid      (net_00_to_10_valid),
        .east_out_packet     (net_00_to_10_packet),
        .east_out_ready      (net_00_to_10_ready),

        // West: Perimeter Edge
        .west_in_valid       (1'b0),
        .west_in_packet      ({PACKET_WIDTH{1'b0}}),
        .west_in_ready       (),
        .west_out_valid      (),
        .west_out_packet     (),
        .west_out_ready      (1'b1)
    );

    // =========================================================================
    // 4. Instantiate Node (1, 0) — Top-Right
    // =========================================================================
    lif_mesh_node_2d #(
        .TILE_X       (1),
        .TILE_Y       (0),
        .COORD_WIDTH  (3),
        .AXON_WIDTH   (3),
        .PACKET_WIDTH (PACKET_WIDTH),
        .WEIGHT_WIDTH (WEIGHT_WIDTH),
        .MEM_WIDTH    (MEM_WIDTH)
    ) u_node_10 (
        .clk                 (clk),
        .rst_n               (rst_n),
        .timestep_tick       (timestep_tick),
        .cfg_we              (cfg_we && (cfg_node_sel == 2'b01)),
        .cfg_addr            (cfg_addr),
        .cfg_wdata           (cfg_wdata),
        .cfg_rdata           (rdata_10),
        .v_threshold         (v_threshold),
        .v_rest              (v_rest),
        .routing_table       (routing_table_10),
        .tile_spikes_out     (node10_spikes),
        .tile_refractory_bus (node10_refractory),

        // North: Perimeter Edge
        .north_in_valid      (1'b0),
        .north_in_packet     ({PACKET_WIDTH{1'b0}}),
        .north_in_ready      (),
        .north_out_valid     (),
        .north_out_packet    (),
        .north_out_ready     (1'b1),

        // South: Connected to Node (1, 1)
        .south_in_valid      (net_11_to_10_valid),
        .south_in_packet     (net_11_to_10_packet),
        .south_in_ready      (net_11_to_10_ready),
        .south_out_valid     (net_10_to_11_valid),
        .south_out_packet    (net_10_to_11_packet),
        .south_out_ready     (net_10_to_11_ready),

        // East: Perimeter Edge
        .east_in_valid       (1'b0),
        .east_in_packet      ({PACKET_WIDTH{1'b0}}),
        .east_in_ready       (),
        .east_out_valid      (),
        .east_out_packet     (),
        .east_out_ready      (1'b1),

        // West: Connected to Node (0, 0)
        .west_in_valid       (net_00_to_10_valid),
        .west_in_packet      (net_00_to_10_packet),
        .west_in_ready       (net_00_to_10_ready),
        .west_out_valid      (net_10_to_00_valid),
        .west_out_packet     (net_10_to_00_packet),
        .west_out_ready      (net_10_to_00_ready)
    );

    // =========================================================================
    // 5. Instantiate Node (0, 1) — Bottom-Left
    // =========================================================================
    lif_mesh_node_2d #(
        .TILE_X       (0),
        .TILE_Y       (1),
        .COORD_WIDTH  (3),
        .AXON_WIDTH   (3),
        .PACKET_WIDTH (PACKET_WIDTH),
        .WEIGHT_WIDTH (WEIGHT_WIDTH),
        .MEM_WIDTH    (MEM_WIDTH)
    ) u_node_01 (
        .clk                 (clk),
        .rst_n               (rst_n),
        .timestep_tick       (timestep_tick),
        .cfg_we              (cfg_we && (cfg_node_sel == 2'b10)),
        .cfg_addr            (cfg_addr),
        .cfg_wdata           (cfg_wdata),
        .cfg_rdata           (rdata_01),
        .v_threshold         (v_threshold),
        .v_rest              (v_rest),
        .routing_table       (routing_table_01),
        .tile_spikes_out     (node01_spikes),
        .tile_refractory_bus (node01_refractory),

        // North: Connected to Node (0, 0)
        .north_in_valid      (net_00_to_01_valid),
        .north_in_packet     (net_00_to_01_packet),
        .north_in_ready      (net_00_to_01_ready),
        .north_out_valid     (net_01_to_00_valid),
        .north_out_packet    (net_01_to_00_packet),
        .north_out_ready     (net_01_to_00_ready),

        // South: Perimeter Edge
        .south_in_valid      (1'b0),
        .south_in_packet     ({PACKET_WIDTH{1'b0}}),
        .south_in_ready      (),
        .south_out_valid     (),
        .south_out_packet    (),
        .south_out_ready     (1'b1),

        // East: Connected to Node (1, 1)
        .east_in_valid       (net_11_to_01_valid),
        .east_in_packet      (net_11_to_01_packet),
        .east_in_ready       (net_11_to_01_ready),
        .east_out_valid      (net_01_to_11_valid),
        .east_out_packet     (net_01_to_11_packet),
        .east_out_ready      (net_01_to_11_ready),

        // West: Perimeter Edge
        .west_in_valid       (1'b0),
        .west_in_packet      ({PACKET_WIDTH{1'b0}}),
        .west_in_ready       (),
        .west_out_valid      (),
        .west_out_packet     (),
        .west_out_ready      (1'b1)
    );

    // =========================================================================
    // 6. Instantiate Node (1, 1) — Bottom-Right
    // =========================================================================
    lif_mesh_node_2d #(
        .TILE_X       (1),
        .TILE_Y       (1),
        .COORD_WIDTH  (3),
        .AXON_WIDTH   (3),
        .PACKET_WIDTH (PACKET_WIDTH),
        .WEIGHT_WIDTH (WEIGHT_WIDTH),
        .MEM_WIDTH    (MEM_WIDTH)
    ) u_node_11 (
        .clk                 (clk),
        .rst_n               (rst_n),
        .timestep_tick       (timestep_tick),
        .cfg_we              (cfg_we && (cfg_node_sel == 2'b11)),
        .cfg_addr            (cfg_addr),
        .cfg_wdata           (cfg_wdata),
        .cfg_rdata           (rdata_11),
        .v_threshold         (v_threshold),
        .v_rest              (v_rest),
        .routing_table       (routing_table_11),
        .tile_spikes_out     (node11_spikes),
        .tile_refractory_bus (node11_refractory),

        // North: Connected to Node (1, 0)
        .north_in_valid      (net_10_to_11_valid),
        .north_in_packet     (net_10_to_11_packet),
        .north_in_ready      (net_10_to_11_ready),
        .north_out_valid     (net_11_to_10_valid),
        .north_out_packet    (net_11_to_10_packet),
        .north_out_ready     (net_11_to_10_ready),

        // South: Perimeter Edge
        .south_in_valid      (1'b0),
        .south_in_packet     ({PACKET_WIDTH{1'b0}}),
        .south_in_ready      (),
        .south_out_valid     (),
        .south_out_packet    (),
        .south_out_ready     (1'b1),

        // East: Perimeter Edge
        .east_in_valid       (1'b0),
        .east_in_packet      ({PACKET_WIDTH{1'b0}}),
        .east_in_ready       (),
        .east_out_valid      (),
        .east_out_packet     (),
        .east_out_ready      (1'b1),

        // West: Connected to Node (0, 1)
        .west_in_valid       (net_01_to_11_valid),
        .west_in_packet      (net_01_to_11_packet),
        .west_in_ready       (net_01_to_11_ready),
        .west_out_valid      (net_11_to_01_valid),
        .west_out_packet     (net_11_to_01_packet),
        .west_out_ready      (net_11_to_01_ready)
    );

endmodule
