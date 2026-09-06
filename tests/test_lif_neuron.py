"""test_lif_neuron.py — Asynchronous Cocotb verification testbench for Leaky Integrate-and-Fire neuron."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def test_lif_leaky_decay(dut):
    """Test 1: Verify exponential leak decay in the absence of input spikes."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Apply reset on falling edge for clean synchronous timing
    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.spike_in_valid.value = 0
    dut.synaptic_weight.value = 0
    dut.v_threshold.value = 1000
    dut.v_rest.value = 0
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    assert int(dut.v_mem.value) == 0, f"Expected v_mem=0, got {dut.v_mem.value}"
    assert int(dut.spike_out.value) == 0

    # Inject charge: +800 mV (stimulus set on falling edge)
    dut.spike_in_valid.value = 1
    dut.synaptic_weight.value = 800
    await FallingEdge(dut.clk)
    dut.spike_in_valid.value = 0
    dut.synaptic_weight.value = 0

    # Cycle 1 after injection: v_mem should be 800
    v1 = int(dut.v_mem.value.signed_integer)
    assert v1 == 800, f"Expected 800, got {v1}"

    # Cycle 2: Let it leak! leak_amount = 800 >> 3 = 100. Expected v_mem = 800 - 100 = 700
    await FallingEdge(dut.clk)
    v2 = int(dut.v_mem.value.signed_integer)
    expected_v2 = 800 - (800 >> 3)
    assert v2 == expected_v2, f"Leak failed: expected {expected_v2}, got {v2}"

    # Cycle 3: 700 - (700 >> 3) = 700 - 87 = 613
    await FallingEdge(dut.clk)
    v3 = int(dut.v_mem.value.signed_integer)
    expected_v3 = 700 - (700 >> 3)
    assert v3 == expected_v3, f"Leak failed: expected {expected_v3}, got {v3}"


@cocotb.test()
async def test_lif_threshold_firing_and_subtractive_reset(dut):
    """Test 2: Verify threshold crossing, output spike, and subtractive residual retention."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.spike_in_valid.value = 0
    dut.synaptic_weight.value = 0
    dut.v_threshold.value = 1000
    dut.v_rest.value = 0
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    # Inject +1200 mV (exceeds threshold 1000 by 200 mV)
    dut.spike_in_valid.value = 1
    dut.synaptic_weight.value = 1200
    await FallingEdge(dut.clk)
    dut.spike_in_valid.value = 0
    dut.synaptic_weight.value = 0

    # The neuron should fire!
    assert int(dut.spike_out.value) == 1, "Neuron failed to emit spike when Vmem >= Vth!"
    
    # Subtractive reset verification: residual should be 1200 - 1000 = 200 mV
    v_post = int(dut.v_mem.value.signed_integer)
    assert v_post == 200, f"Subtractive reset failed: expected 200 mV residual, got {v_post}"
    assert int(dut.in_refractory.value) == 1, "Neuron should be in refractory state after firing"


@cocotb.test()
async def test_lif_refractory_period(dut):
    """Test 3: Verify refractory dead-time blocks incoming spikes."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.v_threshold.value = 500
    dut.v_rest.value = 0
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    # Trigger spike
    dut.spike_in_valid.value = 1
    dut.synaptic_weight.value = 500
    await FallingEdge(dut.clk)
    assert int(dut.spike_out.value) == 1
    assert int(dut.in_refractory.value) == 1

    # Try to inject another spike immediately during refractory cycle 1
    dut.spike_in_valid.value = 1
    dut.synaptic_weight.value = 999
    await FallingEdge(dut.clk)
    
    # Input spike MUST be ignored during refractory
    assert int(dut.spike_out.value) == 0, "Spike fired during refractory period!"

    # Refractory cycle 2
    dut.spike_in_valid.value = 0
    await FallingEdge(dut.clk)
    assert int(dut.spike_out.value) == 0

    # Neuron exits refractory
    await FallingEdge(dut.clk)
    assert int(dut.in_refractory.value) == 0, "Neuron failed to exit refractory dead-time"


@cocotb.test()
async def test_lif_lower_bound_clamping(dut):
    """Test 4: Verify negative inhibitory weights clamp at resting potential."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
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
