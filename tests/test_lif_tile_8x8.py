"""test_lif_tile_8x8.py — Asynchronous Cocotb verification testbench for 8x8 LIF Spiking Core Tile."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def test_tile_config_programming_and_readback(dut):
    """Test 1: Verify SRAM-like configuration port writes and registered readbacks for all 64 synapses."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Apply reset
    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.timestep_tick.value = 0
    dut.spike_in_valid.value = 0
    dut.axon_spikes_in.value = 0
    dut.cfg_we.value = 0
    dut.cfg_addr.value = 0
    dut.cfg_wdata.value = 0
    dut.v_threshold.value = 1000
    dut.v_rest.value = 0
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    # Program a deterministic matrix of signed INT8 weights
    expected_weights = {}
    for r in range(8):
        for c in range(8):
            # Signed 8-bit weight between -100 and +100
            val = ((r * 17) - (c * 23)) % 201 - 100
            expected_weights[(r, c)] = val
            
            addr = (r << 3) | c
            dut.cfg_we.value = 1
            dut.cfg_addr.value = addr
            dut.cfg_wdata.value = val
            await FallingEdge(dut.clk)

    dut.cfg_we.value = 0
    await FallingEdge(dut.clk)

    # Read back and verify all 64 weights
    for r in range(8):
        for c in range(8):
            addr = (r << 3) | c
            dut.cfg_addr.value = addr
            await FallingEdge(dut.clk) # Registered readback latency: 1 cycle
            read_val = int(dut.cfg_rdata.value.to_signed())
            exp_val = expected_weights[(r, c)]
            assert read_val == exp_val, f"Mismatch at ({r},{c}): expected {exp_val}, got {read_val}"


@cocotb.test()
async def test_tile_column_ingress_and_pipeline_sum(dut):
    """Test 2: Verify Option 1C parallel column adder tree and Option 2B registered pipeline staging."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.timestep_tick.value = 0
    dut.spike_in_valid.value = 0
    dut.axon_spikes_in.value = 0
    dut.cfg_we.value = 0
    dut.v_threshold.value = 1000
    dut.v_rest.value = 0
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    # Program column 0 with specific weights:
    # Row 0: +25, Row 1: +35, Row 2: -15, Row 3: +45, Rows 4..7: 0
    test_weights = [25, 35, -15, 45, 0, 0, 0, 0]
    for r in range(8):
        dut.cfg_we.value = 1
        dut.cfg_addr.value = (r << 3) | 0
        dut.cfg_wdata.value = test_weights[r]
        await FallingEdge(dut.clk)

    dut.cfg_we.value = 0
    await FallingEdge(dut.clk)

    # Fire Axons 0, 1, 2, 3: expected sum = 25 + 35 - 15 + 45 = +90
    dut.spike_in_valid.value = 1
    dut.axon_spikes_in.value = 0b00001111 # Rows 0..3 active
    await FallingEdge(dut.clk)
    dut.spike_in_valid.value = 0
    dut.axon_spikes_in.value = 0

    # Pipeline Stage 1 completed: check internal pipeline register for column 0
    col0_pipe = int(dut.col_sum_pipe[0].value.to_signed())
    assert col0_pipe == 90, f"Pipeline adder sum failed: expected 90, got {col0_pipe}"

    # Cycle 2: Neuron 0 completes integration
    await FallingEdge(dut.clk)
    v_mem_0 = int(dut.gen_lif_neurons[0].u_neuron.v_mem.value.to_signed())
    assert v_mem_0 == 90, f"Neuron 0 membrane integration failed: expected 90, got {v_mem_0}"


@cocotb.test()
async def test_tile_parallel_firing_and_subtractive_reset(dut):
    """Test 3: Verify all 8 neurons firing in parallel with subtractive reset and refractory bus assertion."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.timestep_tick.value = 0
    dut.spike_in_valid.value = 0
    dut.axon_spikes_in.value = 0
    dut.cfg_we.value = 0
    dut.v_threshold.value = 1000
    dut.v_rest.value = 0
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    # Configure diagonal matrix: W[i, i] = 1200 / 10 = +120
    # If all 8 axons fire, each neuron i receives +120 from its diagonal synapse?
    # Wait: let's program 10 rows? No, there are 8 rows.
    # If W[r, c] = +120 for all 8 rows on each column: sum = 8 * 120 = +960 (not quite 1000).
    # Since weights are signed INT8, max weight is +127!
    # If all 8 rows have W[r, c] = +125 on column c:
    # Column sum = 8 * 125 = +1000 (crosses threshold 1000!).
    # Let's set W[r, c] = +127: sum = 8 * 127 = +1016 (exceeds threshold 1000 by 16 mV).
    for r in range(8):
        for c in range(8):
            dut.cfg_we.value = 1
            dut.cfg_addr.value = (r << 3) | c
            dut.cfg_wdata.value = 127
            await FallingEdge(dut.clk)

    dut.cfg_we.value = 0
    await FallingEdge(dut.clk)

    # Stimulate all 8 axons simultaneously in timestep 1
    dut.spike_in_valid.value = 1
    dut.axon_spikes_in.value = 0xFF
    dut.timestep_tick.value = 1 # Timestep boundary strobe accompanies ingress
    await FallingEdge(dut.clk)
    dut.spike_in_valid.value = 0
    dut.axon_spikes_in.value = 0
    dut.timestep_tick.value = 0

    # Pipeline latency: wait 1 cycle for neurons to consume pipelined inputs & evaluate firing
    await FallingEdge(dut.clk)

    # All 8 neurons must fire simultaneously!
    spikes = int(dut.neuron_spikes_out.value)
    assert spikes == 0xFF, f"Parallel firing failed: expected 0xFF, got 0x{spikes:02X}"

    # All 8 neurons must now be in refractory
    refrac = int(dut.in_refractory_bus.value)
    assert refrac == 0xFF, f"Refractory bus assertion failed: expected 0xFF, got 0x{refrac:02X}"

    # Subtractive reset residual check: 1016 - 1000 = 16 mV on all neurons
    for n in range(8):
        v_res = int(dut.gen_lif_neurons[n].u_neuron.v_mem.value.to_signed())
        assert v_res == 16, f"Neuron {n} residual failed: expected 16, got {v_res}"


@cocotb.test()
async def test_tile_refractory_recovery(dut):
    """Test 4: Verify refractory dead-time recovery across the tile after REFRACTORY_CYCLES timesteps."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.timestep_tick.value = 0
    dut.spike_in_valid.value = 0
    dut.axon_spikes_in.value = 0
    dut.cfg_we.value = 0
    dut.v_threshold.value = 500
    dut.v_rest.value = 0
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    # Program weights of 100 across 6 rows -> 600 mV > 500 mV threshold
    for r in range(6):
        for c in range(8):
            dut.cfg_we.value = 1
            dut.cfg_addr.value = (r << 3) | c
            dut.cfg_wdata.value = 100
            await FallingEdge(dut.clk)

    dut.cfg_we.value = 0
    await FallingEdge(dut.clk)

    # Fire all neurons
    dut.spike_in_valid.value = 1
    dut.axon_spikes_in.value = 0x3F # Rows 0..5
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.spike_in_valid.value = 0
    dut.axon_spikes_in.value = 0
    dut.timestep_tick.value = 0

    await FallingEdge(dut.clk)
    assert int(dut.neuron_spikes_out.value) == 0xFF
    assert int(dut.in_refractory_bus.value) == 0xFF

    # Advance Timestep 1: Refractory decrements (2 -> 1)
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0
    await FallingEdge(dut.clk) # Allow pipeline register to settle
    assert int(dut.in_refractory_bus.value) == 0xFF, "Neurons should still be in refractory (cycle 1 of 2)"

    # Advance Timestep 2: Refractory decrements (1 -> 0)
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0
    await FallingEdge(dut.clk)
    assert int(dut.in_refractory_bus.value) == 0x00, "Neurons should have exited refractory dead-time"
