"""test_lif_mesh_2x2.py — Industrial Cocotb Verification Suite for 4-Core 2D Neuromorphic Mesh SoC."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


def pack_routing_table(entries):
    """Packs 8 entries of (dst_x, dst_y, dst_axon) into a 72-bit vector.
    Each entry is 9 bits: dst_x[8:6], dst_y[5:3], dst_axon[2:0]."""
    table = 0
    for i in range(8):
        dst_x, dst_y, dst_axon = entries[i] if i < len(entries) else (0, 0, 0)
        entry_val = ((dst_x & 0x7) << 6) | ((dst_y & 0x7) << 3) | (dst_axon & 0x7)
        table |= (entry_val << (i * 9))
    return table


async def reset_mesh_soc(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.timestep_tick.value = 0
    dut.cfg_node_sel.value = 0
    dut.cfg_we.value = 0
    dut.cfg_addr.value = 0
    dut.cfg_wdata.value = 0
    dut.v_threshold.value = 100
    dut.v_rest.value = 0

    dut.routing_table_00.value = 0
    dut.routing_table_10.value = 0
    dut.routing_table_01.value = 0
    dut.routing_table_11.value = 0

    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


@cocotb.test()
async def test_mesh_config_programming_and_readback(dut):
    """Test 1: Verify memory-mapped configuration write and readback across all 4 cores (256 synapses)."""
    await reset_mesh_soc(dut)

    expected = {}
    for node in range(4):
        for addr in range(16): # Sample first 16 synapses per tile
            val = ((node + 1) * 15 + addr * 3) % 120 - 40
            expected[(node, addr)] = val

            dut.cfg_node_sel.value = node
            dut.cfg_we.value = 1
            dut.cfg_addr.value = addr
            dut.cfg_wdata.value = val
            await FallingEdge(dut.clk)

    dut.cfg_we.value = 0
    await FallingEdge(dut.clk)

    # Readback verification
    for node in range(4):
        for addr in range(16):
            dut.cfg_node_sel.value = node
            dut.cfg_addr.value = addr
            await FallingEdge(dut.clk)
            read_val = int(dut.cfg_rdata.value.to_signed())
            exp_val = expected[(node, addr)]
            assert read_val == exp_val, f"Mismatch at Node {node}, Addr {addr}: exp {exp_val}, got {read_val}"


@cocotb.test()
async def test_mesh_horizontal_routing_hop(dut):
    """Test 2: Horizontal 1-hop routing — Node (0, 0) -> East Link -> Node (1, 0)."""
    await reset_mesh_soc(dut)

    # 1. Program routing table for Node (0, 0): Neuron 0 routes to Node (1, 0), Axon 3
    routes_00 = [(1, 0, 3)] + [(0, 0, 0)] * 7
    dut.routing_table_00.value = pack_routing_table(routes_00)

    # 2. Program Node (1, 0) synaptic weight for Row 3, Col 0 = +80
    dut.cfg_node_sel.value = 1 # Node (1, 0)
    dut.cfg_we.value = 1
    dut.cfg_addr.value = (3 << 3) | 0
    dut.cfg_wdata.value = 80
    await FallingEdge(dut.clk)
    dut.cfg_we.value = 0

    # 3. Stimulate Node (0, 0) neuron 0 to fire by injecting internal membrane potential
    # Directly deposit charge on Node 00 neuron 0
    await FallingEdge(dut.clk)
    dut.u_node_00.u_tile.gen_lif_neurons[0].u_neuron.v_mem.value = 150 # Above threshold (100)

    # Issue timestep tick to fire the spike in Node (0, 0)
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0

    # Wait 6 cycles for serialization, NoC East transmission, and arrival at Node (1, 0)
    for _ in range(6):
        await FallingEdge(dut.clk)

    # Node (1, 0) axon 3 must have integrated into neuron 0
    v_mem_10 = int(dut.u_node_10.u_tile.gen_lif_neurons[0].u_neuron.v_mem.value.to_signed())
    assert v_mem_10 > 0, f"Horizontal routing failed: Node (1, 0) neuron 0 v_mem is {v_mem_10}"


@cocotb.test()
async def test_mesh_vertical_routing_hop(dut):
    """Test 3: Vertical 1-hop routing — Node (0, 0) -> South Link -> Node (0, 1)."""
    await reset_mesh_soc(dut)

    # 1. Program routing table for Node (0, 0): Neuron 1 routes to Node (0, 1), Axon 5
    routes_00 = [(0, 0, 0), (0, 1, 5)] + [(0, 0, 0)] * 6
    dut.routing_table_00.value = pack_routing_table(routes_00)

    # 2. Program Node (0, 1) synaptic weight for Row 5, Col 2 = +75
    dut.cfg_node_sel.value = 2 # Node (0, 1)
    dut.cfg_we.value = 1
    dut.cfg_addr.value = (5 << 3) | 2
    dut.cfg_wdata.value = 75
    await FallingEdge(dut.clk)
    dut.cfg_we.value = 0

    # 3. Stimulate Node (0, 0) neuron 1 to fire
    await FallingEdge(dut.clk)
    dut.u_node_00.u_tile.gen_lif_neurons[1].u_neuron.v_mem.value = 150
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0

    # Wait for South transmission, ingress decoding, and 2-cycle pipeline integration
    for _ in range(10):
        await FallingEdge(dut.clk)

    v_mem_01 = int(dut.u_node_01.u_tile.gen_lif_neurons[2].u_neuron.v_mem.value.to_signed())
    assert v_mem_01 > 0, f"Vertical routing failed: Node (0, 1) neuron 2 v_mem is {v_mem_01}"


@cocotb.test()
async def test_mesh_diagonal_two_hop_cascade(dut):
    """Test 4: Diagonal Multi-Hop DOR Routing — Node (0, 0) -> East (1, 0) -> South (1, 1)."""
    await reset_mesh_soc(dut)

    # 1. Program routing table for Node (0, 0): Neuron 4 routes diagonally to Node (1, 1), Axon 1
    routes_00 = [(0, 0, 0)] * 4 + [(1, 1, 1)] + [(0, 0, 0)] * 3
    dut.routing_table_00.value = pack_routing_table(routes_00)

    # 2. Program Node (1, 1) synaptic weight for Row 1, Col 4 = +110 (sufficient to cause firing!)
    dut.cfg_node_sel.value = 3 # Node (1, 1)
    dut.cfg_we.value = 1
    dut.cfg_addr.value = (1 << 3) | 4
    dut.cfg_wdata.value = 110
    await FallingEdge(dut.clk)
    dut.cfg_we.value = 0

    # 3. Fire Node (0, 0) neuron 4
    await FallingEdge(dut.clk)
    dut.u_node_00.u_tile.gen_lif_neurons[4].u_neuron.v_mem.value = 180
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0

    # Wait for 2-hop DOR propagation across NoC: (0,0) -> (1,0) -> (1,1)
    for _ in range(10):
        await FallingEdge(dut.clk)

    # Tick Node (1, 1) to evaluate the integrated spike
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0

    # Verify that Node (1, 1) neuron 4 received charge or fired
    v_mem_11 = int(dut.u_node_11.u_tile.gen_lif_neurons[4].u_neuron.v_mem.value.to_signed())
    node11_spikes = int(dut.node11_spikes.value)
    assert (v_mem_11 > 0) or (node11_spikes > 0), (
        f"Diagonal 2-hop cascade failed: Node (1, 1) v_mem={v_mem_11}, spikes={bin(node11_spikes)}"
    )


@cocotb.test()
async def test_mesh_all_nodes_concurrent_traffic(dut):
    """Test 5: Full-Mesh Stress Test — All 4 nodes simultaneously transmitting cross-diagonal spikes."""
    await reset_mesh_soc(dut)

    # Cross-diagonal routing matrix:
    # Node (0,0) -> Node (1,1), Axon 0
    # Node (1,0) -> Node (0,1), Axon 1
    # Node (0,1) -> Node (1,0), Axon 2
    # Node (1,1) -> Node (0,0), Axon 3
    dut.routing_table_00.value = pack_routing_table([(1, 1, 0)] + [(0, 0, 0)] * 7)
    dut.routing_table_10.value = pack_routing_table([(0, 1, 1)] + [(0, 0, 0)] * 7)
    dut.routing_table_01.value = pack_routing_table([(1, 0, 2)] + [(0, 0, 0)] * 7)
    dut.routing_table_11.value = pack_routing_table([(0, 0, 3)] + [(0, 0, 0)] * 7)

    # Program weights at all 4 targets:
    # Node (1,1) Row 0, Col 0 = 60
    # Node (0,1) Row 1, Col 1 = 60
    # Node (1,0) Row 2, Col 2 = 60
    # Node (0,0) Row 3, Col 3 = 60
    targets = [
        (3, (0 << 3) | 0), # Node 11
        (2, (1 << 3) | 1), # Node 01
        (1, (2 << 3) | 2), # Node 10
        (0, (3 << 3) | 3)  # Node 00
    ]
    for node, addr in targets:
        dut.cfg_node_sel.value = node
        dut.cfg_we.value = 1
        dut.cfg_addr.value = addr
        dut.cfg_wdata.value = 60
        await FallingEdge(dut.clk)
    dut.cfg_we.value = 0

    # Simultaneously excite neuron 0 on all 4 nodes
    await FallingEdge(dut.clk)
    dut.u_node_00.u_tile.gen_lif_neurons[0].u_neuron.v_mem.value = 150
    dut.u_node_10.u_tile.gen_lif_neurons[0].u_neuron.v_mem.value = 150
    dut.u_node_01.u_tile.gen_lif_neurons[0].u_neuron.v_mem.value = 150
    dut.u_node_11.u_tile.gen_lif_neurons[0].u_neuron.v_mem.value = 150

    # Fire timestep tick to launch all 4 spikes concurrently into the mesh
    dut.timestep_tick.value = 1
    await FallingEdge(dut.clk)
    dut.timestep_tick.value = 0

    # Wait 14 cycles for complete cross-mesh arbitration, multi-hop routing, and integration
    for _ in range(14):
        await FallingEdge(dut.clk)

    # Check that all 4 target nodes successfully integrated their incoming spikes
    v_11 = int(dut.u_node_11.u_tile.gen_lif_neurons[0].u_neuron.v_mem.value.to_signed())
    v_01 = int(dut.u_node_01.u_tile.gen_lif_neurons[1].u_neuron.v_mem.value.to_signed())
    v_10 = int(dut.u_node_10.u_tile.gen_lif_neurons[2].u_neuron.v_mem.value.to_signed())
    v_00 = int(dut.u_node_00.u_tile.gen_lif_neurons[3].u_neuron.v_mem.value.to_signed())

    assert v_11 > 0, f"Node (1,1) missed cross-traffic spike: v_mem={v_11}"
    assert v_01 > 0, f"Node (0,1) missed cross-traffic spike: v_mem={v_01}"
    assert v_10 > 0, f"Node (1,0) missed cross-traffic spike: v_mem={v_10}"
    assert v_00 > 0, f"Node (0,0) missed cross-traffic spike: v_mem={v_00}"

