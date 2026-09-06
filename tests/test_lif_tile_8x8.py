"""test_lif_tile_8x8.py — Industrial-grade Cocotb verification testbench for 8x8 LIF Spiking Core Tile."""

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

try:
    from tests.golden_lif_model import GoldenLifTile
except ImportError:
    from golden_lif_model import GoldenLifTile


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

    # Configure weights: +127 across all 8 rows on all columns
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
    dut.timestep_tick.value = 1
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
    await FallingEdge(dut.clk)
    assert int(dut.in_refractory_bus.value) == 0xFF, "Neurons should still be in refractory (cycle 1 of 2)"

    # Advance Timestep 2: Refractory decrements (1 -> 0)
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0
    await FallingEdge(dut.clk)
    assert int(dut.in_refractory_bus.value) == 0x00, "Neurons should have exited refractory dead-time"


@cocotb.test()
async def test_tile_crv_poisson_profile_c_500_timesteps(dut):
    """Test 5: Industrial CRV — 500-timestep Profile C Poisson sparsity sweep with cycle-accurate golden scoreboard."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())
    random.seed(0xDEADBEEF)

    # Initialize golden model
    golden = GoldenLifTile(
        weight_width=8,
        mem_width=16,
        leak_shift=3,
        refractory_cycles=2,
        v_threshold=800,
        v_rest=0,
    )

    # Apply reset
    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.timestep_tick.value = 0
    dut.spike_in_valid.value = 0
    dut.axon_spikes_in.value = 0
    dut.cfg_we.value = 0
    dut.v_threshold.value = 800
    dut.v_rest.value = 0
    golden.reset()
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    # Program randomized weights across the array
    for r in range(8):
        for c in range(8):
            w = random.randint(-40, 90)
            golden.program_weight(r, c, w)
            dut.cfg_we.value = 1
            dut.cfg_addr.value = (r << 3) | c
            dut.cfg_wdata.value = w
            await FallingEdge(dut.clk)

    dut.cfg_we.value = 0
    await FallingEdge(dut.clk)

    total_spikes_fired = 0

    # 500 Timesteps with Profile C Sparsity Schedule
    for step in range(500):
        if step < 100:
            prob = 0.10
        elif step < 200:
            prob = 0.30
        elif step < 300:
            prob = 0.75
        elif step < 400:
            prob = 0.90
        else:
            prob = 0.00

        # Cycle 1: Ingress injection
        spikes = 0
        for r in range(8):
            if random.random() < prob:
                spikes |= (1 << r)

        spike_valid = 1 if spikes != 0 else 0

        dut.axon_spikes_in.value = spikes
        dut.spike_in_valid.value = spike_valid
        dut.timestep_tick.value = 0

        golden_spk, golden_vmem, golden_refrac = golden.step(
            axon_spikes=spikes,
            spike_in_valid=bool(spike_valid),
            timestep_tick=False,
        )

        await FallingEdge(dut.clk)
        dut_spk = int(dut.neuron_spikes_out.value)
        dut_refrac = int(dut.in_refractory_bus.value)
        exp_spk = sum(s << n for n, s in enumerate(golden_spk))
        exp_refrac = sum(r << n for n, r in enumerate(golden_refrac))
        assert dut_spk == exp_spk, f"Step {step} cycle 1 spike mismatch: DUT=0x{dut_spk:02X}, Golden=0x{exp_spk:02X}"
        assert dut_refrac == exp_refrac, f"Step {step} cycle 1 refrac mismatch: DUT=0x{dut_refrac:02X}, Golden=0x{exp_refrac:02X}"
        total_spikes_fired += bin(dut_spk).count("1")

        # Cycle 2: Timestep tick evaluation
        dut.axon_spikes_in.value = 0
        dut.spike_in_valid.value = 0
        dut.timestep_tick.value = 1

        golden_spk, golden_vmem, golden_refrac = golden.step(
            axon_spikes=0,
            spike_in_valid=False,
            timestep_tick=True,
        )

        await FallingEdge(dut.clk)
        dut.timestep_tick.value = 0

        dut_spk = int(dut.neuron_spikes_out.value)
        dut_refrac = int(dut.in_refractory_bus.value)
        exp_spk = sum(s << n for n, s in enumerate(golden_spk))
        exp_refrac = sum(r << n for n, r in enumerate(golden_refrac))
        assert dut_spk == exp_spk, f"Step {step} cycle 2 spike mismatch: DUT=0x{dut_spk:02X}, Golden=0x{exp_spk:02X}"
        assert dut_refrac == exp_refrac, f"Step {step} cycle 2 refrac mismatch: DUT=0x{dut_refrac:02X}, Golden=0x{exp_refrac:02X}"

        # Internal membrane potential lockstep assertion across all 8 neurons
        for n in range(8):
            v_dut = int(dut.gen_lif_neurons[n].u_neuron.v_mem.value.to_signed())
            assert v_dut == golden_vmem[n], f"Step {step} Neuron {n} Vmem mismatch: DUT={v_dut}, Golden={golden_vmem[n]}"

        total_spikes_fired += bin(dut_spk).count("1")

    dut._log.info(f"CRV 500-Timestep verification complete! Total spikes emitted: {total_spikes_fired}")
    assert total_spikes_fired > 50, "Tile fired too few spikes during dense excitation phases"


@cocotb.test()
async def test_tile_corner_case_positive_saturation_clamp(dut):
    """Test 6: Corner Case — Verify positive saturation clamping at +32767 without overflow rollover."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.timestep_tick.value = 0
    dut.spike_in_valid.value = 0
    dut.axon_spikes_in.value = 0
    dut.cfg_we.value = 0
    dut.v_threshold.value = 32767
    dut.v_rest.value = 0
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    # Program all weights to +127
    for r in range(8):
        for c in range(8):
            dut.cfg_we.value = 1
            dut.cfg_addr.value = (r << 3) | c
            dut.cfg_wdata.value = 127
            await FallingEdge(dut.clk)
    dut.cfg_we.value = 0
    await FallingEdge(dut.clk)

    # Drive maximum input current (+1016 per cycle) without ticking for 40 cycles
    dut.spike_in_valid.value = 1
    dut.axon_spikes_in.value = 0xFF
    for _ in range(40):
        await FallingEdge(dut.clk)

    await FallingEdge(dut.clk)

    # Every neuron must clamp at exactly +32767 (MAX_POS)
    for n in range(8):
        v_mem = int(dut.gen_lif_neurons[n].u_neuron.v_mem.value.to_signed())
        assert v_mem == 32767, f"Positive saturation failed: expected 32767, got {v_mem}"


@cocotb.test()
async def test_tile_corner_case_negative_hyperpolarization_clamp(dut):
    """Test 7: Corner Case — Verify lower bound clamping at v_rest = 0 under massive inhibitory currents."""
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

    # Program all weights to -128 (maximum negative inhibition)
    for r in range(8):
        for c in range(8):
            dut.cfg_we.value = 1
            dut.cfg_addr.value = (r << 3) | c
            dut.cfg_wdata.value = -128
            await FallingEdge(dut.clk)
    dut.cfg_we.value = 0
    await FallingEdge(dut.clk)

    # Drive massive negative current (-1024 per cycle) for 30 cycles
    dut.spike_in_valid.value = 1
    dut.axon_spikes_in.value = 0xFF
    for _ in range(30):
        await FallingEdge(dut.clk)

    await FallingEdge(dut.clk)

    # Membrane must never drop below 0
    for n in range(8):
        v_mem = int(dut.gen_lif_neurons[n].u_neuron.v_mem.value.to_signed())
        assert v_mem == 0, f"Lower bound clamping failed: expected 0, got {v_mem}"


@cocotb.test()
async def test_tile_concurrent_config_write_hazard(dut):
    """Test 8: Hazard Verification — Verify dynamic weight reconfiguration during live axon spike streaming."""
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

    # Initialize all weights to +10
    for r in range(8):
        for c in range(8):
            dut.cfg_we.value = 1
            dut.cfg_addr.value = (r << 3) | c
            dut.cfg_wdata.value = 10
            await FallingEdge(dut.clk)

    # Now continuously stream spikes on Row 0
    dut.spike_in_valid.value = 1
    dut.axon_spikes_in.value = 0x01 # Only row 0

    # Concurrently reconfigure W[0, 3] from +10 to +80 while streaming!
    dut.cfg_we.value = 1
    dut.cfg_addr.value = (0 << 3) | 3
    dut.cfg_wdata.value = 80
    await FallingEdge(dut.clk)
    dut.cfg_we.value = 0

    # Wait 2 cycles for pipeline update and integration
    await FallingEdge(dut.clk)
    await FallingEdge(dut.clk)

    # All neurons must continue integrating properly without corruption
    for n in range(8):
        v_mem = int(dut.gen_lif_neurons[n].u_neuron.v_mem.value.to_signed())
        assert v_mem > 0, f"Neuron {n} failed to integrate"
