"""test_lif_tile_uvm.py — Top-level PyUVM Test for LIF 8x8 Neuromorphic Core Tile."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer
from pyuvm import (
    uvm_env,
    uvm_test,
    uvm_sequencer,
    uvm_root,
    ConfigDB
)
from tests.uvm.lif_driver import LifTileDriver
from tests.uvm.lif_monitor import LifTileMonitor
from tests.uvm.lif_scoreboard import LifTileScoreboard
from tests.uvm.lif_sequences import (
    TileConfigSequence,
    PoissonCRVSequence,
    DirectedCornerCoverageSequence
)


class LifTileEnv(uvm_env):
    """Encapsulates Sequencer, Driver, Monitor, and Scoreboard into a unified UVM verification environment."""

    def build_phase(self):
        super().build_phase()
        self.seqr = uvm_sequencer("seqr", self)
        self.driver = LifTileDriver("driver", self)
        self.monitor = LifTileMonitor("monitor", self)
        self.scoreboard = LifTileScoreboard("scoreboard", self)

    def connect_phase(self):
        super().connect_phase()
        self.driver.seq_item_port.connect(self.seqr.seq_item_export)
        self.monitor.ap.connect(self.scoreboard.fifo_mon.analysis_export)


class LifTileUvmTest(uvm_test):
    """Top-level UVM Test running multi-sequence verification with CRV and coverage closure."""

    def build_phase(self):
        super().build_phase()
        self.env = LifTileEnv("env", self)

    async def run_phase(self):
        self.raise_objection()
        dut = cocotb.top

        # ----------------------------------------------------------------------
        # Phase 1: Synaptic Weight Crossbar Configuration
        # ----------------------------------------------------------------------
        self.logger.info("Executing UVM Sequence: TileConfigSequence (64 Synapses)...")
        cfg_seq = TileConfigSequence("cfg_seq")
        await cfg_seq.start(self.env.seqr)

        # ----------------------------------------------------------------------
        # Phase 2: Constrained-Random Verification (CRV) Poisson Stimulus
        # ----------------------------------------------------------------------
        self.logger.info("Executing UVM Sequence: PoissonCRVSequence (60 Timesteps)...")
        crv_seq = PoissonCRVSequence("crv_seq", num_timesteps=60, cycles_per_step=4)
        await crv_seq.start(self.env.seqr)

        # ----------------------------------------------------------------------
        # Phase 3: Coverage-Driven Feedback Loop (Targeted Corner Cases)
        # ----------------------------------------------------------------------
        self.logger.info("Executing UVM Sequence: DirectedCornerCoverageSequence...")
        corner_seq = DirectedCornerCoverageSequence("corner_seq")
        await corner_seq.start(self.env.seqr)

        # Allow pipeline to drain and final spikes to be captured
        for _ in range(12):
            await FallingEdge(dut.clk)

        self.drop_objection()


@cocotb.test()
async def run_uvm_verification_suite(dut):
    """Cocotb entrypoint instantiating the PyUVM hierarchy and running the test."""
    # 1. Start Free-Running Clock (100 MHz, 10 ns period)
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # 2. Apply Asynchronous Deterministic Hardware Reset
    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.timestep_tick.value = 0
    dut.spike_in_valid.value = 0
    dut.axon_spikes_in.value = 0
    dut.cfg_we.value = 0
    dut.cfg_addr.value = 0
    dut.cfg_wdata.value = 0
    dut.v_threshold.value = 100
    dut.v_rest.value = 0

    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    # 3. Launch PyUVM Standard Test Hierarchy
    await uvm_root().run_test("LifTileUvmTest")
