`timescale 1ns / 1ps

/**
 * lif_neuron.v — Synthesizable Leaky Integrate-and-Fire (LIF) Spiking Neuron
 *
 * Implements discrete-time leaky integration with multiplier-free bit-shift decay,
 * subtractive reset (Vmem = Vmem - Vth), refractory dead-time lock, and signed saturation.
 *
 * Biological / SNN Formula:
 *   V[t] = V[t-1] - (V[t-1] >>> LEAK_SHIFT) + I_syn[t]
 *   if (V[t] >= V_th):
 *       Spike = 1
 *       V[t] = V[t] - V_th
 *       refractory_counter = REFRACTORY_CYCLES
 */
module lif_neuron #(
    parameter integer WIDTH             = 16, // Bitwidth of membrane potential (signed)
    parameter integer LEAK_SHIFT        = 3,  // beta = 1 - 2^(-LEAK_SHIFT) -> 1 - 1/8 = 0.875
    parameter integer REFRACTORY_CYCLES = 2   // Inactive dead-time cycles after spike
)(
    input  wire                     clk,
    input  wire                     rst_n,

    // Timestep Synchronization
    input  wire                     timestep_tick,   // Algorithmic timestep boundary strobe (triggers decay & firing eval)

    // Synaptic Stimulus
    input  wire                     spike_in_valid,  // Strobe indicating synaptic input active
    input  wire signed [WIDTH-1:0]  synaptic_weight, // Signed synaptic input current (I_syn)

    // Dynamic Neuron Parameters
    input  wire signed [WIDTH-1:0]  v_threshold,     // Firing threshold (e.g. +1000)
    input  wire signed [WIDTH-1:0]  v_rest,          // Resting potential / lower floor clamp (e.g. 0)

    // Neuron Outputs
    output reg                      spike_out,       // Event spike pulse (1 cycle, emitted on timestep_tick)
    output reg  signed [WIDTH-1:0]  v_mem,           // Current membrane potential state
    output wire                     in_refractory    // Status: 1 if neuron in dead-time
);

    // Internal Refractory Counter (measured in algorithmic timesteps)
    reg [3:0] refrac_cnt;
    assign in_refractory = (refrac_cnt > 4'd0);

    // Saturation constant
    localparam signed [WIDTH-1:0] MAX_POS = {1'b0, {(WIDTH-1){1'b1}}}; // +32767 for 16-bit

    // Explicitly sized (WIDTH+1)-bit operands to prevent signed width truncation/expansion mismatches
    wire signed [WIDTH:0] v_thresh_ext = {v_threshold[WIDTH-1], v_threshold};
    wire signed [WIDTH:0] v_rest_ext   = {v_rest[WIDTH-1], v_rest};
    wire signed [WIDTH:0] max_pos_ext  = {1'b0, MAX_POS};
    wire signed [WIDTH:0] syn_ext      = {synaptic_weight[WIDTH-1], synaptic_weight};
    wire signed [WIDTH:0] v_mem_ext    = {v_mem[WIDTH-1], v_mem};

    // Intermediate wires for arithmetic and saturation
    wire signed [WIDTH-1:0] leak_amount;
    wire signed [WIDTH:0]   v_decayed;
    wire signed [WIDTH:0]   base_potential;
    wire signed [WIDTH:0]   v_next;
    wire signed [WIDTH:0]   v_after_reset;
    wire                    will_fire;

    // Shift-based leakage: V_leak = V_mem >>> LEAK_SHIFT (only if above resting potential)
    assign leak_amount = (v_mem > v_rest) ? (v_mem >>> LEAK_SHIFT) : {WIDTH{1'b0}};
    assign v_decayed   = v_mem_ext - {leak_amount[WIDTH-1], leak_amount};

    // Base potential: decays only when timestep_tick is asserted; otherwise preserves v_mem
    assign base_potential = timestep_tick ? v_decayed : v_mem_ext;

    // Add incoming synaptic weight if valid and not in refractory dead-time
    assign v_next = (spike_in_valid && !in_refractory) ? (base_potential + syn_ext) : base_potential;

    // Subtractive reset: deduct threshold from integrated membrane potential
    assign v_after_reset = v_next - v_thresh_ext;

    // Firing condition: strictly evaluated on timestep_tick boundary
    assign will_fire = timestep_tick && (!in_refractory) && (v_next >= v_thresh_ext);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v_mem      <= v_rest;
            spike_out  <= 1'b0;
            refrac_cnt <= 4'd0;
        end else begin
            // Default pulse de-assertion
            spike_out <= 1'b0;

            if (will_fire) begin
                // --- THRESHOLD CROSSED ON TIMESTEP TICK: FIRE SPIKE ---
                spike_out  <= 1'b1;
                refrac_cnt <= REFRACTORY_CYCLES[3:0];

                // Subtractive reset with lower resting clamp and saturation guard
                if (v_after_reset < v_rest_ext) begin
                    v_mem <= v_rest;
                end else if (v_after_reset > max_pos_ext) begin
                    v_mem <= MAX_POS;
                end else begin
                    v_mem <= v_after_reset[WIDTH-1:0];
                end
            end else begin
                // --- NO SPIKE ---
                // Decrement refractory counter only when algorithmic timestep advances
                if (timestep_tick && (refrac_cnt > 4'd0)) begin
                    refrac_cnt <= refrac_cnt - 4'd1;
                end

                // Clamp lower bound to resting potential and upper bound to MAX_POS
                if (v_next < v_rest_ext) begin
                    v_mem <= v_rest;
                end else if (v_next > max_pos_ext) begin
                    v_mem <= MAX_POS; // Positive saturation
                end else begin
                    v_mem <= v_next[WIDTH-1:0];
                end
            end
        end
    end

endmodule
