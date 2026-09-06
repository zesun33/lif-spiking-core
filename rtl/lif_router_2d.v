// =============================================================================
// Module: lif_router_2d
// Description: 5-Port 2D Mesh NoC Router for Inter-Tile AER Spiking Networks.
//              Implements Dimension-Order Routing (DOR: X-then-Y) and
//              Round-Robin arbitration with Virtual Cut-Through input FIFOs.
// Ports:
//   0: Local Core Tile
//   1: North Link
//   2: South Link
//   3: East Link
//   4: West Link
// =============================================================================

`timescale 1ns / 1ps

module lif_router_2d #(
    parameter TILE_X       = 0,
    parameter TILE_Y       = 0,
    parameter COORD_WIDTH  = 3,
    parameter AXON_WIDTH   = 3,
    parameter PACKET_WIDTH = 16,
    parameter FIFO_DEPTH   = 4
)(
    input  wire                             clk,
    input  wire                             rst_n,

    // Port 0: Local Neuromorphic Tile
    input  wire                             local_in_valid,
    input  wire [PACKET_WIDTH-1:0]          local_in_packet,
    output wire                             local_in_ready,

    output reg                              local_out_valid,
    output reg  [PACKET_WIDTH-1:0]          local_out_packet,
    input  wire                             local_out_ready,

    // Port 1: North Link
    input  wire                             north_in_valid,
    input  wire [PACKET_WIDTH-1:0]          north_in_packet,
    output wire                             north_in_ready,

    output reg                              north_out_valid,
    output reg  [PACKET_WIDTH-1:0]          north_out_packet,
    input  wire                             north_out_ready,

    // Port 2: South Link
    input  wire                             south_in_valid,
    input  wire [PACKET_WIDTH-1:0]          south_in_packet,
    output wire                             south_in_ready,

    output reg                              south_out_valid,
    output reg  [PACKET_WIDTH-1:0]          south_out_packet,
    input  wire                             south_out_ready,

    // Port 3: East Link
    input  wire                             east_in_valid,
    input  wire [PACKET_WIDTH-1:0]          east_in_packet,
    output wire                             east_in_ready,

    output reg                              east_out_valid,
    output reg  [PACKET_WIDTH-1:0]          east_out_packet,
    input  wire                             east_out_ready,

    // Port 4: West Link
    input  wire                             west_in_valid,
    input  wire [PACKET_WIDTH-1:0]          west_in_packet,
    output wire                             west_in_ready,

    output reg                              west_out_valid,
    output reg  [PACKET_WIDTH-1:0]          west_out_packet,
    input  wire                             west_out_ready
);

    // =========================================================================
    // 1. Pack Arrays for Ingress and Egress Signals
    // =========================================================================
    wire                    in_valid  [0:4];
    wire [PACKET_WIDTH-1:0] in_packet [0:4];
    wire                    in_ready  [0:4];

    reg                     out_valid [0:4];
    reg  [PACKET_WIDTH-1:0] out_packet[0:4];
    wire                    out_ready [0:4];

    assign in_valid[0] = local_in_valid;
    assign in_valid[1] = north_in_valid;
    assign in_valid[2] = south_in_valid;
    assign in_valid[3] = east_in_valid;
    assign in_valid[4] = west_in_valid;

    assign in_packet[0] = local_in_packet;
    assign in_packet[1] = north_in_packet;
    assign in_packet[2] = south_in_packet;
    assign in_packet[3] = east_in_packet;
    assign in_packet[4] = west_in_packet;

    assign local_in_ready = in_ready[0];
    assign north_in_ready = in_ready[1];
    assign south_in_ready = in_ready[2];
    assign east_in_ready  = in_ready[3];
    assign west_in_ready  = in_ready[4];

    assign out_ready[0] = local_out_ready;
    assign out_ready[1] = north_out_ready;
    assign out_ready[2] = south_out_ready;
    assign out_ready[3] = east_out_ready;
    assign out_ready[4] = west_out_ready;

    always @(*) begin
        local_out_valid  = out_valid[0];
        local_out_packet = out_packet[0];
        north_out_valid  = out_valid[1];
        north_out_packet = out_packet[1];
        south_out_valid  = out_valid[2];
        south_out_packet = out_packet[2];
        east_out_valid   = out_valid[3];
        east_out_packet  = out_packet[3];
        west_out_valid   = out_valid[4];
        west_out_packet  = out_packet[4];
    end

    // =========================================================================
    // 2. Input Buffers (Synchronous FIFOs with Depth 4)
    // =========================================================================
    wire [PACKET_WIDTH-1:0] fifo_rdata [0:4];
    wire                    fifo_empty [0:4];
    wire                    fifo_full  [0:4];
    reg                     fifo_pop   [0:4];

    genvar p;
    generate
        for (p = 0; p < 5; p = p + 1) begin : gen_input_fifos
            reg [PACKET_WIDTH-1:0] mem [0:FIFO_DEPTH-1];
            reg [1:0] wptr;
            reg [1:0] rptr;
            reg [2:0] count;

            assign fifo_empty[p] = (count == 3'd0);
            assign fifo_full[p]  = (count == FIFO_DEPTH[2:0]);
            assign in_ready[p]   = !fifo_full[p];
            assign fifo_rdata[p] = mem[rptr];

            integer i;
            always @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    wptr  <= 2'd0;
                    rptr  <= 2'd0;
                    count <= 3'd0;
                    for (i = 0; i < FIFO_DEPTH; i = i + 1) begin
                        mem[i] <= {PACKET_WIDTH{1'b0}};
                    end
                end else begin
                    // Write transaction
                    if (in_valid[p] && in_ready[p]) begin
                        mem[wptr] <= in_packet[p];
                        wptr <= (wptr == FIFO_DEPTH-1) ? 2'd0 : wptr + 2'd1;
                    end

                    // Read transaction
                    if (fifo_pop[p] && !fifo_empty[p]) begin
                        rptr <= (rptr == FIFO_DEPTH-1) ? 2'd0 : rptr + 2'd1;
                    end

                    // Count update
                    case ({in_valid[p] && in_ready[p], fifo_pop[p] && !fifo_empty[p]})
                        2'b10: count <= count + 3'd1;
                        2'b01: count <= count - 3'd1;
                        default: count <= count;
                    endcase
                end
            end
        end
    endgenerate

    // =========================================================================
    // 3. Dimension-Order Routing (DOR: X-then-Y)
    // =========================================================================
    reg [2:0] target_port [0:4];
    reg       request     [0:4];

    integer k;
    always @(*) begin
        for (k = 0; k < 5; k = k + 1) begin
            if (!fifo_empty[k]) begin
                request[k] = 1'b1;
                // Decode destination from packet: dst_x = [14:12], dst_y = [11:9]
                if (fifo_rdata[k][14:12] > TILE_X[2:0]) begin
                    target_port[k] = 3'd3; // East
                end else if (fifo_rdata[k][14:12] < TILE_X[2:0]) begin
                    target_port[k] = 3'd4; // West
                end else if (fifo_rdata[k][11:9] > TILE_Y[2:0]) begin
                    target_port[k] = 3'd2; // South
                end else if (fifo_rdata[k][11:9] < TILE_Y[2:0]) begin
                    target_port[k] = 3'd1; // North
                end else begin
                    target_port[k] = 3'd0; // Local
                end
            end else begin
                request[k] = 1'b0;
                target_port[k] = 3'd0;
            end
        end
    end

    // =========================================================================
    // 4. Egress Crossbar & Round-Robin Arbitration per Output Port
    // =========================================================================
    reg [2:0] rr_priority [0:4];
    reg [2:0] granted_src [0:4];
    reg       has_grant   [0:4];

    reg [2:0] cand_src;
    reg [3:0] cand_sum;

    integer ep, ip;
    always @(*) begin
        // Default assignments
        for (ep = 0; ep < 5; ep = ep + 1) begin
            has_grant[ep]   = 1'b0;
            granted_src[ep] = 3'd0;
            out_valid[ep]   = 1'b0;
            out_packet[ep]  = {PACKET_WIDTH{1'b0}};
        end

        for (ip = 0; ip < 5; ip = ip + 1) begin
            fifo_pop[ip] = 1'b0;
        end

        // Egress port arbitration
        for (ep = 0; ep < 5; ep = ep + 1) begin
            // Round-robin search starting from rr_priority[ep]
            for (ip = 0; ip < 5; ip = ip + 1) begin
                if (!has_grant[ep]) begin
                    cand_sum = {1'b0, rr_priority[ep]} + ip[3:0];
                    cand_src = (cand_sum >= 4'd5) ? (cand_sum[2:0] - 3'd5) : cand_sum[2:0];
                    case (cand_src)
                        3'd0: if (request[0] && (target_port[0] == ep[2:0])) begin has_grant[ep] = 1'b1; granted_src[ep] = 3'd0; end
                        3'd1: if (request[1] && (target_port[1] == ep[2:0])) begin has_grant[ep] = 1'b1; granted_src[ep] = 3'd1; end
                        3'd2: if (request[2] && (target_port[2] == ep[2:0])) begin has_grant[ep] = 1'b1; granted_src[ep] = 3'd2; end
                        3'd3: if (request[3] && (target_port[3] == ep[2:0])) begin has_grant[ep] = 1'b1; granted_src[ep] = 3'd3; end
                        3'd4: if (request[4] && (target_port[4] == ep[2:0])) begin has_grant[ep] = 1'b1; granted_src[ep] = 3'd4; end
                        default: ;
                    endcase
                end
            end

            // If grant achieved and downstream ready, forward packet and pop input FIFO
            if (has_grant[ep]) begin
                out_valid[ep]  = 1'b1;
                out_packet[ep] = fifo_rdata[granted_src[ep]];
                if (out_ready[ep]) begin
                    fifo_pop[granted_src[ep]] = 1'b1;
                end
            end
        end
    end

    // Round-robin pointer updates
    integer e_idx;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (e_idx = 0; e_idx < 5; e_idx = e_idx + 1) begin
                rr_priority[e_idx] <= 3'd0;
            end
        end else begin
            for (e_idx = 0; e_idx < 5; e_idx = e_idx + 1) begin
                if (has_grant[e_idx] && out_ready[e_idx]) begin
                    rr_priority[e_idx] <= (granted_src[e_idx] == 3'd4) ? 3'd0 : granted_src[e_idx] + 3'd1;
                end
            end
        end
    end

endmodule
