"""golden_lif_model.py — Bit-accurate Golden Reference Model for lif_tile_8x8.

Used for industrial-grade Constrained-Random Verification (CRV) and cycle-accurate
lockstep assertion scoreboards.
"""

from typing import Dict, List, Tuple


class GoldenLifTile:
    """Bit-accurate software model of lif_tile_8x8.v with Option 1C ingress and Option 2B pipeline."""

    def __init__(
        self,
        weight_width: int = 8,
        mem_width: int = 16,
        leak_shift: int = 3,
        refractory_cycles: int = 2,
        v_threshold: int = 1000,
        v_rest: int = 0,
    ):
        self.weight_width = weight_width
        self.mem_width = mem_width
        self.leak_shift = leak_shift
        self.refractory_cycles = refractory_cycles
        self.v_threshold = v_threshold
        self.v_rest = v_rest

        self.max_pos = (1 << (mem_width - 1)) - 1  # +32767 for 16-bit

        # State storage
        self.weights = [[0 for _ in range(8)] for _ in range(8)]
        self.v_mem = [v_rest for _ in range(8)]
        self.refrac_cnt = [0 for _ in range(8)]
        self.spike_out = [0 for _ in range(8)]

        # Pipeline registers (Option 2B)
        self.col_sum_pipe = [0 for _ in range(8)]
        self.col_valid_pipe = False
        self.timestep_tick_pipe = False

    def reset(self):
        """Synchronous/Asynchronous reset."""
        for r in range(8):
            for c in range(8):
                self.weights[r][c] = 0
        for n in range(8):
            self.v_mem[n] = self.v_rest
            self.refrac_cnt[n] = 0
            self.spike_out[n] = 0
        for c in range(8):
            self.col_sum_pipe[c] = 0
        self.col_valid_pipe = False
        self.timestep_tick_pipe = False

    def program_weight(self, row: int, col: int, weight: int):
        """Configure weight directly."""
        assert -128 <= weight <= 127, f"Weight {weight} out of INT8 range"
        self.weights[row][col] = weight

    def step(
        self,
        axon_spikes: int,
        spike_in_valid: bool,
        timestep_tick: bool,
        cfg_we: bool = False,
        cfg_addr: int = 0,
        cfg_wdata: int = 0,
    ) -> Tuple[List[int], List[int], List[int]]:
        """Simulate one rising clock edge with pipelined execution.
        
        Returns:
            (spike_out [8], v_mem [8], in_refractory [8])
        """
        # --- STAGE 1 COMBINATIONAL: Compute column sums from axon spikes ---
        col_sum_comb = [0 for _ in range(8)]
        for c in range(8):
            c_sum = 0
            for r in range(8):
                if (axon_spikes >> r) & 1:
                    c_sum += self.weights[r][c]
            col_sum_comb[c] = c_sum
        col_valid_comb = bool(spike_in_valid and (axon_spikes != 0))

        # --- STAGE 2 NEURON UPDATE: Process inputs from PIPELINE registers ---
        current_in_refractory = [1 if self.refrac_cnt[n] > 0 else 0 for n in range(8)]

        for n in range(8):
            # 1. Leak decay calculation
            if self.v_mem[n] > self.v_rest:
                leak_amount = self.v_mem[n] >> self.leak_shift
            else:
                leak_amount = 0
            v_decayed = self.v_mem[n] - leak_amount

            # Base potential: decays only when pipelined timestep_tick is active
            base_potential = v_decayed if self.timestep_tick_pipe else self.v_mem[n]

            # 2. Integration
            if self.col_valid_pipe and not current_in_refractory[n]:
                v_next = base_potential + self.col_sum_pipe[n]
            else:
                v_next = base_potential

            # 3. Firing condition
            will_fire = bool(
                self.timestep_tick_pipe
                and (not current_in_refractory[n])
                and (v_next >= self.v_threshold)
            )

            if will_fire:
                self.spike_out[n] = 1
                self.refrac_cnt[n] = self.refractory_cycles
                v_after_reset = v_next - self.v_threshold
                # Saturation and clamping
                if v_after_reset < self.v_rest:
                    self.v_mem[n] = self.v_rest
                elif v_after_reset > self.max_pos:
                    self.v_mem[n] = self.max_pos
                else:
                    self.v_mem[n] = v_after_reset
            else:
                self.spike_out[n] = 0
                if self.timestep_tick_pipe and self.refrac_cnt[n] > 0:
                    self.refrac_cnt[n] -= 1
                
                # Lower clamp and upper saturation
                if v_next < self.v_rest:
                    self.v_mem[n] = self.v_rest
                elif v_next > self.max_pos:
                    self.v_mem[n] = self.max_pos
                else:
                    self.v_mem[n] = v_next

        # --- UPDATE PIPELINE REGISTERS FOR NEXT CYCLE ---
        for c in range(8):
            self.col_sum_pipe[c] = col_sum_comb[c]
        self.col_valid_pipe = col_valid_comb
        self.timestep_tick_pipe = timestep_tick

        # --- HANDLE SYNAPTIC CONFIGURATION WRITE ---
        if cfg_we:
            row = (cfg_addr >> 3) & 0x7
            col = cfg_addr & 0x7
            self.weights[row][col] = cfg_wdata

        updated_in_refractory = [1 if self.refrac_cnt[n] > 0 else 0 for n in range(8)]
        return list(self.spike_out), list(self.v_mem), updated_in_refractory
