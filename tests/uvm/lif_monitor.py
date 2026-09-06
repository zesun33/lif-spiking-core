"""lif_monitor.py — PyUVM Passive Monitor for LIF Core Tile."""

import cocotb
from cocotb.triggers import RisingEdge
from pyuvm import uvm_monitor, uvm_analysis_port
from tests.uvm.lif_seq_item import NeuronSpikeSeqItem


class LifTileMonitor(uvm_monitor):
    """Passively samples egress spikes and refractory states on rising clock edges."""

    def build_phase(self):
        super().build_phase()
        self.dut = cocotb.top
        self.ap = uvm_analysis_port("ap", self)

    async def run_phase(self):
        while True:
            await RisingEdge(self.dut.clk)
            # Sample synchronous outputs on rising edge
            spike_mask = int(self.dut.neuron_spikes_out.value)
            refractory_mask = int(self.dut.in_refractory_bus.value)

            item = NeuronSpikeSeqItem(
                name="mon_egress_item",
                spike_mask=spike_mask,
                refractory_mask=refractory_mask
            )
            self.ap.write(item)
