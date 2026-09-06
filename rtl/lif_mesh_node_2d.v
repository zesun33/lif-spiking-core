// =============================================================================
// Module: lif_mesh_node_2d
// Description: Integrated 2D Mesh Neuromorphic Node combining an 8x8 LIF Core
//              Tile with a 5-Port AER Router and bidirectional spike translation.
// =============================================================================

`timescale 1ns / 1ps

module lif_mesh_node_2d #(
    parameter TILE_X       = 0,
    parameter TILE_Y       = 0,
    parameter COORD_WIDTH  = 3,
    parameter AXON_WIDTH   = 3,
    parameter PACKET_WIDTH = 16,
    parameter WEIGHT_WIDTH = 8,
    parameter MEM_WIDTH    = 16
)(
    input  wire                             clk,
    input  wire                             rst_n,

    // Algorithmic Timestep Synchronization
    input  wire                             timestep_tick,

    // SRAM Synaptic Configuration Port
    input  wire                             cfg_we,
    input  wire [5:0]                       cfg_addr,
    input  wire signed [WEIGHT_WIDTH-1:0]   cfg_wdata,
    output wire signed [WEIGHT_WIDTH-1:0]   cfg_rdata,

    // Hyperparameters
    input  wire signed [MEM_WIDTH-1:0]      v_threshold,
    input  wire signed [MEM_WIDTH-1:0]      v_rest,

    // Static Routing Table: Where does neuron i send its spikes?
    // [i]: {dst_x[2:0], dst_y[2:0], dst_axon[2:0]}
    input  wire [8*(2*COORD_WIDTH+AXON_WIDTH)-1:0] routing_table,

    // Direct Tile Status Egress
    output wire [7:0]                       tile_spikes_out,
    output wire [7:0]                       tile_refractory_bus,

    // --- External Network Mesh Links (N, S, E, W) ---
    // Port 1: North Link
    input  wire                             north_in_valid,
    input  wire [PACKET_WIDTH-1:0]          north_in_packet,
    output wire                             north_in_ready,
    output wire                             north_out_valid,
    output wire [PACKET_WIDTH-1:0]          north_out_packet,
    input  wire                             north_out_ready,

    // Port 2: South Link
    input  wire                             south_in_valid,
    input  wire [PACKET_WIDTH-1:0]          south_in_packet,
    output wire                             south_in_ready,
    output wire                             south_out_valid,
    output wire [PACKET_WIDTH-1:0]          south_out_packet,
    input  wire                             south_out_ready,

    // Port 3: East Link
    input  wire                             east_in_valid,
    input  wire [PACKET_WIDTH-1:0]          east_in_packet,
    output wire                             east_in_ready,
    output wire                             east_out_valid,
    output wire [PACKET_WIDTH-1:0]          east_out_packet,
    input  wire                             east_out_ready,

    // Port 4: West Link
    input  wire                             west_in_valid,
    input  wire [PACKET_WIDTH-1:0]          west_in_packet,
    output wire                             west_in_ready,
    output wire                             west_out_valid,
    output wire [PACKET_WIDTH-1:0]          west_out_packet,
    input  wire                             west_out_ready
);

    // =========================================================================
    // 1. Internal Interconnect Signals
    // =========================================================================
    wire                    router_local_in_valid;
    wire [PACKET_WIDTH-1:0] router_local_in_packet;
    wire                    router_local_in_ready;

    wire                    router_local_out_valid;
    wire [PACKET_WIDTH-1:0] router_local_out_packet;
    reg                     router_local_out_ready;

    reg                     tile_spike_in_valid;
    reg  [7:0]              tile_axon_spikes_in;
    wire [7:0]              raw_neuron_spikes;

    assign tile_spikes_out = raw_neuron_spikes;

    // =========================================================================
    // 2. Instantiate 5-Port 2D Mesh AER Router
    // =========================================================================
    lif_router_2d #(
        .TILE_X       (TILE_X),
        .TILE_Y       (TILE_Y),
        .COORD_WIDTH  (COORD_WIDTH),
        .AXON_WIDTH   (AXON_WIDTH),
        .PACKET_WIDTH (PACKET_WIDTH),
        .FIFO_DEPTH   (4)
    ) u_router (
        .clk              (clk),
        .rst_n            (rst_n),

        .local_in_valid   (router_local_in_valid),
        .local_in_packet  (router_local_in_packet),
        .local_in_ready   (router_local_in_ready),

        .local_out_valid  (router_local_out_valid),
        .local_out_packet (router_local_out_packet),
        .local_out_ready  (router_local_out_ready),

        .north_in_valid   (north_in_valid),
        .north_in_packet  (north_in_packet),
        .north_in_ready   (north_in_ready),
        .north_out_valid  (north_out_valid),
        .north_out_packet (north_out_packet),
        .north_out_ready  (north_out_ready),

        .south_in_valid   (south_in_valid),
        .south_in_packet  (south_in_packet),
        .south_in_ready   (south_in_ready),
        .south_out_valid  (south_out_valid),
        .south_out_packet (south_out_packet),
        .south_out_ready  (south_out_ready),

        .east_in_valid    (east_in_valid),
        .east_in_packet   (east_in_packet),
        .east_in_ready    (east_in_ready),
        .east_out_valid   (east_out_valid),
        .east_out_packet  (east_out_packet),
        .east_out_ready   (east_out_ready),

        .west_in_valid    (west_in_valid),
        .west_in_packet   (west_in_packet),
        .west_in_ready    (west_in_ready),
        .west_out_valid   (west_out_valid),
        .west_out_packet  (west_out_packet),
        .west_out_ready   (west_out_ready)
    );

    // =========================================================================
    // 3. Egress AER Packetizer (Neuron Spikes -> Router Local In)
    // Serializes up to 8 parallel neuron spikes into AER packets
    // =========================================================================
    reg [7:0] pending_spikes;
    reg [2:0] serialize_idx;
    reg       tx_active;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pending_spikes <= 8'd0;
            serialize_idx  <= 3'd0;
            tx_active      <= 1'b0;
        end else begin
            if (raw_neuron_spikes != 8'd0) begin
                pending_spikes <= pending_spikes | raw_neuron_spikes;
                tx_active      <= 1'b1;
            end else if (tx_active && router_local_in_ready && pending_spikes[serialize_idx]) begin
                pending_spikes[serialize_idx] <= 1'b0;
                if (pending_spikes == (8'd1 << serialize_idx)) begin
                    tx_active <= 1'b0;
                end
            end

            if (tx_active) begin
                if (serialize_idx == 3'd7) begin
                    serialize_idx <= 3'd0;
                end else begin
                    serialize_idx <= serialize_idx + 3'd1;
                end
            end
        end
    end

    // Extract routing destination from table for the active neuron
    wire [8:0] route_entry = routing_table[serialize_idx*9 +: 9];
    wire [2:0] target_dst_x = route_entry[8:6];
    wire [2:0] target_dst_y = route_entry[5:3];
    wire [2:0] target_axon  = route_entry[2:0];

    assign router_local_in_valid = tx_active && pending_spikes[serialize_idx];
    assign router_local_in_packet = {
        1'b1,
        target_dst_x,
        target_dst_y,
        target_axon,
        TILE_X[2:0],
        TILE_Y[2:0]
    };

    // =========================================================================
    // 4. Ingress AER Depacketizer (Router Local Out -> Tile Axon Inputs)
    // =========================================================================
    always @(*) begin
        router_local_out_ready = 1'b1;
        if (router_local_out_valid) begin
            tile_spike_in_valid = 1'b1;
            tile_axon_spikes_in = (8'd1 << router_local_out_packet[8:6]); // Decoded axon
        end else begin
            tile_spike_in_valid = 1'b0;
            tile_axon_spikes_in = 8'd0;
        end
    end

    // =========================================================================
    // 5. Instantiate 8x8 LIF Core Tile
    // =========================================================================
    lif_tile_8x8 #(
        .WEIGHT_WIDTH (WEIGHT_WIDTH),
        .MEM_WIDTH    (MEM_WIDTH)
    ) u_tile (
        .clk               (clk),
        .rst_n             (rst_n),
        .timestep_tick     (timestep_tick),
        .spike_in_valid    (tile_spike_in_valid),
        .axon_spikes_in    (tile_axon_spikes_in),
        .cfg_we            (cfg_we),
        .cfg_addr          (cfg_addr),
        .cfg_wdata         (cfg_wdata),
        .cfg_rdata         (cfg_rdata),
        .v_threshold       (v_threshold),
        .v_rest            (v_rest),
        .neuron_spikes_out (raw_neuron_spikes),
        .in_refractory_bus (tile_refractory_bus)
    );

endmodule
