"""lif_driver.py — PyUVM Driver (Bus Functional Model) for LIF Core Tile."""

import cocotb
from cocotb.triggers import FallingEdge
from pyuvm import uvm_driver


class LifTileDriver(uvm_driver):
    """Translates high-level sequence items into physical pin transitions on the DUT."""

    def build_phase(self):
        super().build_phase()
        self.dut = cocotb.top

    async def run_phase(self):
        # Initialize input pins to safe default states
        self.dut.spike_in_valid.value = 0
        self.dut.axon_spikes_in.value = 0
        self.dut.timestep_tick.value = 0
        self.dut.cfg_we.value = 0
        self.dut.cfg_addr.value = 0
        self.dut.cfg_wdata.value = 0

        while True:
            item = await self.seq_item_port.get_next_item()
            await FallingEdge(self.dut.clk)

            if item.is_config:
                # Drive SRAM configuration write port
                self.dut.cfg_we.value = 1
                self.dut.cfg_addr.value = item.addr
                self.dut.cfg_wdata.value = item.weight
                self.dut.spike_in_valid.value = 0
                self.dut.axon_spikes_in.value = 0
                self.dut.timestep_tick.value = 0
            else:
                # Drive axon spike ingress & timestep tick
                self.dut.cfg_we.value = 0
                self.dut.spike_in_valid.value = 1 if item.spike_vector > 0 else 0
                self.dut.axon_spikes_in.value = item.spike_vector
                self.dut.timestep_tick.value = item.timestep_tick

            self.seq_item_port.item_done()
