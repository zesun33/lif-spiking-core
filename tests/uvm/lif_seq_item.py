"""lif_seq_item.py — UVM Sequence Items for LIF Neuromorphic Core Tile."""

from pyuvm import uvm_sequence_item


class AxonSpikeSeqItem(uvm_sequence_item):
    """Transaction representing axon spike injection and timestep synchronization."""
    def __init__(self, name="AxonSpikeSeqItem", spike_vector=0, timestep_tick=0):
        super().__init__(name)
        self.spike_vector = spike_vector
        self.timestep_tick = timestep_tick
        self.is_config = False

    def __str__(self):
        return f"{self.get_name()}: spikes=0x{self.spike_vector:02X}, tick={self.timestep_tick}"


class TileConfigSeqItem(uvm_sequence_item):
    """Transaction representing synaptic SRAM configuration write."""
    def __init__(self, name="TileConfigSeqItem", addr=0, weight=0):
        super().__init__(name)
        self.addr = addr
        self.weight = weight
        self.is_config = True

    def __str__(self):
        return f"{self.get_name()}: addr=0x{self.addr:02X}, weight={self.weight}"


class NeuronSpikeSeqItem(uvm_sequence_item):
    """Transaction representing observed output spikes and refractory states."""
    def __init__(self, name="NeuronSpikeSeqItem", spike_mask=0, refractory_mask=0):
        super().__init__(name)
        self.spike_mask = spike_mask
        self.refractory_mask = refractory_mask

    def __str__(self):
        return f"{self.get_name()}: spikes=0x{self.spike_mask:02X}, refractory=0x{self.refractory_mask:02X}"
