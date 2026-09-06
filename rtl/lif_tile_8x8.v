`timescale 1ns / 1ps

/**
 * lif_tile_8x8.v — Synthesizable 8x8 Neuromorphic LIF Spiking Core Tile
 *
 * Architecture:
 *   - Synaptic Storage: 8x8 array of signed INT8 weights (64 synapses, 512 bits).
 *   - Configuration Port: Memory-mapped synchronous write/read interface (cfg_we, cfg_addr, cfg_wdata, cfg_rdata).
 *   - Option 1C Ingress: CIM-style parallel column bitline accumulation.
 *   - Option 2B Pipeline: Registered 1-cycle pipeline stage separating adder tree from neuron accumulators for high Fmax.
 *   - Neuron Array: 8 parallel synthesizable LIF neurons with subtractive reset and leak decay.
 */
module lif_tile_8x8 #(
    parameter integer WEIGHT_WIDTH      = 8,   // Synaptic weight bitwidth (signed INT8)
    parameter integer MEM_WIDTH         = 16,  // Membrane potential bitwidth (signed INT16)
    parameter integer LEAK_SHIFT        = 3,   // beta = 1 - 2^(-LEAK_SHIFT) = 0.875
    parameter integer REFRACTORY_CYCLES = 2    // Inactive dead-time timesteps after spike
)(
    input  wire                               clk,
    input  wire                               rst_n,

    // Algorithmic Timestep Synchronization
    input  wire                               timestep_tick,

    // Axon Spike Ingress (Rows 0..7)
    input  wire                               spike_in_valid,     // Strobe indicating axon_spikes_in is active
    input  wire [7:0]                         axon_spikes_in,     // Bitvector: 1 if axon i fired

    // Synaptic Weight Configuration Port (Synchronous memory-mapped)
    input  wire                               cfg_we,             // Config write enable
    input  wire [5:0]                         cfg_addr,           // Address: [5:3] = row (0..7), [2:0] = col (0..7)
    input  wire signed [WEIGHT_WIDTH-1:0]     cfg_wdata,          // Config write data
    output reg  signed [WEIGHT_WIDTH-1:0]     cfg_rdata,          // Config read data (registered readback)

    // Dynamic Neuron Threshold / Rest (broadcast to all 8 neurons)
    input  wire signed [MEM_WIDTH-1:0]        v_threshold,
    input  wire signed [MEM_WIDTH-1:0]        v_rest,

    // Post-Synaptic Neuron Outputs (Cols 0..7)
    output wire [7:0]                         neuron_spikes_out,  // Bitvector: 1 if neuron j fired
    output wire [7:0]                         in_refractory_bus   // Status: 1 if neuron j in refractory
);

    // =========================================================================
    // 1. Synaptic Weight Matrix Storage (8 rows x 8 columns = 64 weights)
    // =========================================================================
    reg signed [WEIGHT_WIDTH-1:0] weights [0:7][0:7];

    integer r_idx, c_idx;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (r_idx = 0; r_idx < 8; r_idx = r_idx + 1) begin
                for (c_idx = 0; c_idx < 8; c_idx = c_idx + 1) begin
                    weights[r_idx][c_idx] <= {WEIGHT_WIDTH{1'b0}};
                end
            end
            cfg_rdata <= {WEIGHT_WIDTH{1'b0}};
        end else begin
            // Synchronous write
            if (cfg_we) begin
                weights[cfg_addr[5:3]][cfg_addr[2:0]] <= cfg_wdata;
            end
            // Synchronous registered readback
            cfg_rdata <= weights[cfg_addr[5:3]][cfg_addr[2:0]];
        end
    end

    // =========================================================================
    // 2. Spatial Column Adder Trees (8 Parallel Column Reductions)
    //    Level 0: 8-bit gated products
    //    Level 1: 9-bit sums
    //    Level 2: 10-bit sums
    //    Level 3: 11-bit final column current (lossless range -1024 to +1016)
    // =========================================================================
    wire signed [10:0] col_sum_comb [0:7];
    wire               col_valid_comb;

    assign col_valid_comb = spike_in_valid && (|axon_spikes_in);

    genvar c;
    generate
        for (c = 0; c < 8; c = c + 1) begin : gen_col_adder
            // Level 0: Operand isolation / zero-gating based on axon spike
            wire signed [WEIGHT_WIDTH-1:0] p0 = axon_spikes_in[0] ? weights[0][c] : {WEIGHT_WIDTH{1'b0}};
            wire signed [WEIGHT_WIDTH-1:0] p1 = axon_spikes_in[1] ? weights[1][c] : {WEIGHT_WIDTH{1'b0}};
            wire signed [WEIGHT_WIDTH-1:0] p2 = axon_spikes_in[2] ? weights[2][c] : {WEIGHT_WIDTH{1'b0}};
            wire signed [WEIGHT_WIDTH-1:0] p3 = axon_spikes_in[3] ? weights[3][c] : {WEIGHT_WIDTH{1'b0}};
            wire signed [WEIGHT_WIDTH-1:0] p4 = axon_spikes_in[4] ? weights[4][c] : {WEIGHT_WIDTH{1'b0}};
            wire signed [WEIGHT_WIDTH-1:0] p5 = axon_spikes_in[5] ? weights[5][c] : {WEIGHT_WIDTH{1'b0}};
            wire signed [WEIGHT_WIDTH-1:0] p6 = axon_spikes_in[6] ? weights[6][c] : {WEIGHT_WIDTH{1'b0}};
            wire signed [WEIGHT_WIDTH-1:0] p7 = axon_spikes_in[7] ? weights[7][c] : {WEIGHT_WIDTH{1'b0}};

            // Level 1: 9-bit signed adders
            wire signed [8:0] s1_0 = {p0[WEIGHT_WIDTH-1], p0} + {p1[WEIGHT_WIDTH-1], p1};
            wire signed [8:0] s1_1 = {p2[WEIGHT_WIDTH-1], p2} + {p3[WEIGHT_WIDTH-1], p3};
            wire signed [8:0] s1_2 = {p4[WEIGHT_WIDTH-1], p4} + {p5[WEIGHT_WIDTH-1], p5};
            wire signed [8:0] s1_3 = {p6[WEIGHT_WIDTH-1], p6} + {p7[WEIGHT_WIDTH-1], p7};

            // Level 2: 10-bit signed adders
            wire signed [9:0] s2_0 = {s1_0[8], s1_0} + {s1_1[8], s1_1};
            wire signed [9:0] s2_1 = {s1_2[8], s1_2} + {s1_3[8], s1_3};

            // Level 3: 11-bit signed final column sum
            assign col_sum_comb[c] = {s2_0[9], s2_0} + {s2_1[9], s2_1};
        end
    endgenerate

    // =========================================================================
    // 3. Option 2B: Registered Pipeline Stage
    //    Registers column sums and control tokens to break critical path for high Fmax
    // =========================================================================
    reg signed [10:0] col_sum_pipe [0:7];
    reg               col_valid_pipe;
    reg               timestep_tick_pipe;

    integer p_idx;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (p_idx = 0; p_idx < 8; p_idx = p_idx + 1) begin
                col_sum_pipe[p_idx] <= 11'sd0;
            end
            col_valid_pipe     <= 1'b0;
            timestep_tick_pipe <= 1'b0;
        end else begin
            for (p_idx = 0; p_idx < 8; p_idx = p_idx + 1) begin
                col_sum_pipe[p_idx] <= col_sum_comb[p_idx];
            end
            col_valid_pipe     <= col_valid_comb;
            timestep_tick_pipe <= timestep_tick;
        end
    end

    // =========================================================================
    // 4. Parallel LIF Neuron Array (8 Neurons)
    // =========================================================================
    genvar n;
    generate
        for (n = 0; n < 8; n = n + 1) begin : gen_lif_neurons
            // Sign-extend 11-bit column sum to MEM_WIDTH (16-bit)
            wire signed [MEM_WIDTH-1:0] syn_weight_ext = { {(MEM_WIDTH-11){col_sum_pipe[n][10]}}, col_sum_pipe[n] };

            lif_neuron #(
                .WIDTH(MEM_WIDTH),
                .LEAK_SHIFT(LEAK_SHIFT),
                .REFRACTORY_CYCLES(REFRACTORY_CYCLES)
            ) u_neuron (
                .clk(clk),
                .rst_n(rst_n),
                .timestep_tick(timestep_tick_pipe),
                .spike_in_valid(col_valid_pipe),
                .synaptic_weight(syn_weight_ext),
                .v_threshold(v_threshold),
                .v_rest(v_rest),
                .spike_out(neuron_spikes_out[n]),
                .v_mem(), // Internal potential state
                .in_refractory(in_refractory_bus[n])
            );
        end
    endgenerate

endmodule
