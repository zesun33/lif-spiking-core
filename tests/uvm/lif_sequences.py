"""lif_sequences.py — UVM Sequences implementing Constrained-Random (CRV) & Coverage Closure."""

import random
from pyuvm import uvm_sequence
from tests.uvm.lif_seq_item import AxonSpikeSeqItem, TileConfigSeqItem
from tests.uvm.lif_coverage import sample_stimulus_coverage


class TileConfigSequence(uvm_sequence):
    """Programs all 64 synaptic weights in the 8x8 crossbar."""

    def __init__(self, name="TileConfigSequence", weight_matrix=None):
        super().__init__(name)
        self.weight_matrix = weight_matrix

    async def body(self):
        for r in range(8):
            for c in range(8):
                if self.weight_matrix is not None:
                    w = self.weight_matrix[r][c]
                else:
                    w = 50

                item = TileConfigSeqItem(
                    name=f"cfg_s{r}_{c}",
                    addr=(r << 3) | c,
                    weight=w
                )
                await self.start_item(item)
                await self.finish_item(item)


class PoissonCRVSequence(uvm_sequence):
    """Constrained-Random Verification sequence generating biological Poisson spike streams."""

    def __init__(self, name="PoissonCRVSequence", num_timesteps=60, cycles_per_step=4):
        super().__init__(name)
        self.num_timesteps = num_timesteps
        self.cycles_per_step = cycles_per_step

    async def body(self):
        for t in range(self.num_timesteps):
            firing_prob = 0.20 + 0.65 * (t / max(1, self.num_timesteps - 1))

            for cyc in range(self.cycles_per_step):
                spike_vector = 0
                for a in range(8):
                    if random.random() < firing_prob:
                        spike_vector |= (1 << a)

                is_tick = 1 if (cyc >= self.cycles_per_step - 2) else 0

                item = AxonSpikeSeqItem(
                    name=f"axon_t{t}_c{cyc}",
                    spike_vector=spike_vector,
                    timestep_tick=is_tick
                )
                sample_stimulus_coverage(item)
                await self.start_item(item)
                await self.finish_item(item)


class DirectedCornerCoverageSequence(uvm_sequence):
    """Coverage-Driven Feedback Loop: Targeted sequence driving all functional coverage bins to 100%."""

    async def trigger_k_neurons(self, k_count):
        """Helper to program exactly k_count columns with weight 120 and fire them."""
        # 1. Clear all weights
        for r in range(8):
            for c in range(8):
                cfg = TileConfigSeqItem(f"clr_{r}_{c}", addr=(r << 3) | c, weight=0)
                await self.start_item(cfg)
                await self.finish_item(cfg)

        # 2. Program Row 0 for exactly k_count columns
        for c in range(k_count):
            cfg = TileConfigSeqItem(f"set_col{c}", addr=(0 << 3) | c, weight=120)
            await self.start_item(cfg)
            await self.finish_item(cfg)

        # 3. Pipeline Cycle 1: Ingress spike on Row 0
        item = AxonSpikeSeqItem("k_stim_cyc1", spike_vector=0x01, timestep_tick=0)
        sample_stimulus_coverage(item)
        await self.start_item(item)
        await self.finish_item(item)

        # 4. Pipeline Cycle 2: Timestep tick to integrate and fire
        item = AxonSpikeSeqItem("k_stim_cyc2", spike_vector=0x01, timestep_tick=1)
        sample_stimulus_coverage(item)
        await self.start_item(item)
        await self.finish_item(item)

        # 5. Hold tick so neurons evaluate and fire
        item = AxonSpikeSeqItem("k_stim_cyc3", spike_vector=0x00, timestep_tick=1)
        sample_stimulus_coverage(item)
        await self.start_item(item)
        await self.finish_item(item)

        # 6. Wait 5 cycles for full refractory dead-time and recovery
        for _ in range(5):
            item = AxonSpikeSeqItem("k_rec", spike_vector=0x00, timestep_tick=1)
            await self.start_item(item)
            await self.finish_item(item)

    async def body(self):
        # 1. Starvation & Maximum Burst Stimulus Points
        for tick in [0, 1]:
            item = AxonSpikeSeqItem("cov_starvation", spike_vector=0x00, timestep_tick=tick)
            sample_stimulus_coverage(item)
            await self.start_item(item)
            await self.finish_item(item)

            item = AxonSpikeSeqItem("cov_burst", spike_vector=0xFF, timestep_tick=tick)
            sample_stimulus_coverage(item)
            await self.start_item(item)
            await self.finish_item(item)

        # 2. Stimulus density bins: 1, 2, 4 active axons
        for density, mask in [(1, 0x01), (2, 0x03), (4, 0x0F)]:
            for tick in [0, 1]:
                item = AxonSpikeSeqItem(f"cov_dense_{density}", spike_vector=mask, timestep_tick=tick)
                sample_stimulus_coverage(item)
                await self.start_item(item)
                await self.finish_item(item)

        # 3. Directed Output Bins: Trigger exactly 1, 2, 4, and 8 parallel firing neurons
        for k in [1, 2, 4, 8]:
            await self.trigger_k_neurons(k)

        # 4. Concurrent write hazard during active spike
        hazard_cfg = TileConfigSeqItem("hazard_live", addr=0x00, weight=60)
        await self.start_item(hazard_cfg)
        await self.finish_item(hazard_cfg)

        # 5. Final drain
        for _ in range(8):
            item = AxonSpikeSeqItem("final_drain", spike_vector=0x00, timestep_tick=1)
            await self.start_item(item)
            await self.finish_item(item)
