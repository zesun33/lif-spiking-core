"""test_lif_neuron.py — Asynchronous Cocotb verification testbench for Leaky Integrate-and-Fire neuron."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def test_lif_leaky_decay(dut):
    """Test 1: Verify charge holding during intra-timestep cycles and leak decay strictly on timestep_tick."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Apply reset on falling edge
    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.timestep_tick.value = 0
    dut.spike_in_valid.value = 0
    dut.synaptic_weight.value = 0
    dut.v_threshold.value = 1000
    dut.v_rest.value = 0
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    assert int(dut.v_mem.value) == 0, f"Expected v_mem=0, got {dut.v_mem.value}"
    assert int(dut.spike_out.value) == 0

    # Inject charge: +800 mV while timestep_tick = 0 (intra-timestep cycle)
    dut.spike_in_valid.value = 1
    dut.synaptic_weight.value = 800
    await FallingEdge(dut.clk)
    dut.spike_in_valid.value = 0
    dut.synaptic_weight.value = 0

    # Cycle 1 after injection: v_mem should be exactly 800
    v1 = int(dut.v_mem.value.signed_integer)
    assert v1 == 800, f"Expected 800, got {v1}"

    # Cycle 2: Leave timestep_tick = 0. Membrane MUST hold charge without decaying!
    await FallingEdge(dut.clk)
    v2 = int(dut.v_mem.value.signed_integer)
    assert v2 == 800, f"Charge leaked without timestep_tick! Expected 800, got {v2}"

    # Cycle 3: Fire timestep_tick strobe (1 cycle pulse). Now decay occurs!
    # Expected: 800 - (800 >> 3) = 800 - 100 = 700
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0
    v3 = int(dut.v_mem.value.signed_integer)
    assert v3 == 700, f"Leak decay failed on timestep_tick: expected 700, got {v3}"

    # Cycle 4: Second timestep_tick strobe.
    # Expected: 700 - (700 >> 3) = 700 - 87 = 613
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0
    v4 = int(dut.v_mem.value.signed_integer)
    assert v4 == 613, f"Second leak decay failed: expected 613, got {v4}"


@cocotb.test()
async def test_lif_threshold_firing_and_subtractive_reset(dut):
    """Test 2: Verify threshold crossing fires strictly on timestep_tick with subtractive residual retention."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.timestep_tick.value = 0
    dut.spike_in_valid.value = 0
    dut.synaptic_weight.value = 0
    dut.v_threshold.value = 1000
    dut.v_rest.value = 0
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    # Inject +1200 mV (exceeds threshold 1000 by 200 mV) during intra-timestep cycle (timestep_tick = 0)
    dut.spike_in_valid.value = 1
    dut.synaptic_weight.value = 1200
    await FallingEdge(dut.clk)
    dut.spike_in_valid.value = 0
    dut.synaptic_weight.value = 0

    # Intra-cycle check: Membrane is 1200, but neuron MUST NOT fire until timestep_tick arrives!
    assert int(dut.v_mem.value.signed_integer) == 1200
    assert int(dut.spike_out.value) == 0, "Spike fired prematurely before timestep_tick!"

    # Now assert timestep_tick. Decay applies to 1200: 1200 - 150 = 1050.
    # 1050 >= 1000 -> neuron fires! Residual = 1050 - 1000 = 50 mV.
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0

    assert int(dut.spike_out.value) == 1, "Neuron failed to emit spike on timestep_tick!"
    v_post = int(dut.v_mem.value.signed_integer)
    assert v_post == 50, f"Subtractive reset failed: expected 50 mV residual, got {v_post}"
    assert int(dut.in_refractory.value) == 1, "Neuron should be in refractory state after firing"


@cocotb.test()
async def test_lif_refractory_period(dut):
    """Test 3: Verify refractory dead-time decrements strictly on timestep_tick and blocks spikes."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.timestep_tick.value = 0
    dut.v_threshold.value = 500
    dut.v_rest.value = 0
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    # Inject 600 mV directly on timestep_tick to trigger a spike
    dut.timestep_tick.value = 1
    dut.spike_in_valid.value = 1
    dut.synaptic_weight.value = 600
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0
    dut.spike_in_valid.value = 0

    assert int(dut.spike_out.value) == 1
    assert int(dut.in_refractory.value) == 1

    # Intra-timestep cycles: try injecting another spike while in refractory
    dut.spike_in_valid.value = 1
    dut.synaptic_weight.value = 999
    await FallingEdge(dut.clk)
    dut.spike_in_valid.value = 0
    assert int(dut.spike_out.value) == 0
    assert int(dut.in_refractory.value) == 1, "Refractory should persist during intra-cycles"

    # Refractory decrement 1: Advance timestep 1
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0
    assert int(dut.in_refractory.value) == 1, "Should still be in refractory (cycle 1 of 2)"

    # Refractory decrement 2: Advance timestep 2
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0
    assert int(dut.in_refractory.value) == 0, "Neuron should have exited refractory dead-time"


@cocotb.test()
async def test_lif_lower_bound_clamping(dut):
    """Test 4: Verify negative inhibitory weights clamp at resting potential."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.timestep_tick.value = 0
    dut.v_threshold.value = 1000
    dut.v_rest.value = 0
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    # Inject strong negative inhibitory current (-500 mV)
    dut.spike_in_valid.value = 1
    dut.synaptic_weight.value = -500
    await FallingEdge(dut.clk)
    dut.spike_in_valid.value = 0

    # Membrane must NOT be negative; must be clamped at v_rest (0)
    v_mem = int(dut.v_mem.value.signed_integer)
    assert v_mem == 0, f"Lower bound clamping failed: expected 0, got {v_mem}"
