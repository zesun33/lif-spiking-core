"""test_lif_router_2d.py — Industrial Cocotb Verification Suite for 5-Port 2D Mesh AER NoC Router."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


def encode_packet(dst_x, dst_y, axon_id, src_x=0, src_y=0):
    """16-bit packet: {valid[15], dst_x[14:12], dst_y[11:9], axon_id[8:6], src_x[5:3], src_y[2:0]}."""
    return (
        (1 << 15) |
        ((dst_x & 0x7) << 12) |
        ((dst_y & 0x7) << 9) |
        ((axon_id & 0x7) << 6) |
        ((src_x & 0x7) << 3) |
        (src_y & 0x7)
    )


async def reset_router(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.local_in_valid.value = 0
    dut.local_in_packet.value = 0
    dut.local_out_ready.value = 1

    dut.north_in_valid.value = 0
    dut.north_in_packet.value = 0
    dut.north_out_ready.value = 1

    dut.south_in_valid.value = 0
    dut.south_in_packet.value = 0
    dut.south_out_ready.value = 1

    dut.east_in_valid.value = 0
    dut.east_in_packet.value = 0
    dut.east_out_ready.value = 1

    dut.west_in_valid.value = 0
    dut.west_in_packet.value = 0
    dut.west_out_ready.value = 1

    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


@cocotb.test()
async def test_router_dor_east_routing(dut):
    """Test 1: Dimension-Order Routing — Packet destined for (TILE_X+1, TILE_Y) routes East."""
    await reset_router(dut)

    # Inject packet targeting (1, 0) from Local at (0, 0)
    pkt = encode_packet(dst_x=1, dst_y=0, axon_id=4, src_x=0, src_y=0)
    dut.local_in_valid.value = 1
    dut.local_in_packet.value = pkt
    await FallingEdge(dut.clk)
    dut.local_in_valid.value = 0

    # Wait for packet to reach East output
    await RisingEdge(dut.clk)
    assert dut.east_out_valid.value == 1, "Expected packet on East output"
    assert int(dut.east_out_packet.value) == pkt, "Corrupted packet on East output"
    assert dut.north_out_valid.value == 0, "Packet leaked to North"
    assert dut.south_out_valid.value == 0, "Packet leaked to South"
    assert dut.west_out_valid.value == 0, "Packet leaked to West"


@cocotb.test()
async def test_router_dor_south_routing(dut):
    """Test 2: Dimension-Order Routing — Packet destined for (TILE_X, TILE_Y+1) routes South."""
    await reset_router(dut)

    # Inject packet targeting (0, 1) from Local at (0, 0)
    pkt = encode_packet(dst_x=0, dst_y=1, axon_id=2, src_x=0, src_y=0)
    dut.local_in_valid.value = 1
    dut.local_in_packet.value = pkt
    await FallingEdge(dut.clk)
    dut.local_in_valid.value = 0

    await RisingEdge(dut.clk)
    assert dut.south_out_valid.value == 1, "Expected packet on South output"
    assert int(dut.south_out_packet.value) == pkt, "Corrupted packet on South output"


@cocotb.test()
async def test_router_local_delivery(dut):
    """Test 3: Local Delivery — Packet arriving from North destined for (0, 0) delivers to Local."""
    await reset_router(dut)

    pkt = encode_packet(dst_x=0, dst_y=0, axon_id=5, src_x=0, src_y=2)
    dut.north_in_valid.value = 1
    dut.north_in_packet.value = pkt
    await FallingEdge(dut.clk)
    dut.north_in_valid.value = 0

    await RisingEdge(dut.clk)
    assert dut.local_out_valid.value == 1, "Expected packet delivered to Local tile"
    assert int(dut.local_out_packet.value) == pkt, "Corrupted packet delivered to Local"


@cocotb.test()
async def test_router_round_robin_fairness(dut):
    """Test 4: Contention Arbitration — Local and North simultaneously requesting East."""
    await reset_router(dut)

    pkt_local = encode_packet(dst_x=2, dst_y=0, axon_id=1, src_x=0, src_y=0)
    pkt_north = encode_packet(dst_x=2, dst_y=0, axon_id=6, src_x=0, src_y=1)

    # Assert both inputs simultaneously
    dut.local_in_valid.value = 1
    dut.local_in_packet.value = pkt_local
    dut.north_in_valid.value = 1
    dut.north_in_packet.value = pkt_north

    await FallingEdge(dut.clk)
    dut.local_in_valid.value = 0
    dut.north_in_valid.value = 0

    # Cycle 1: First packet must emerge on East
    await RisingEdge(dut.clk)
    assert dut.east_out_valid.value == 1
    p1 = int(dut.east_out_packet.value)

    # Cycle 2: Second packet must emerge on East via round-robin grant
    await RisingEdge(dut.clk)
    assert dut.east_out_valid.value == 1
    p2 = int(dut.east_out_packet.value)

    received = {p1, p2}
    expected = {pkt_local, pkt_north}
    assert received == expected, f"Round-robin dropped or duplicated packets: {received} vs {expected}"


@cocotb.test()
async def test_router_backpressure_and_buffering(dut):
    """Test 5: Flow Control — Downstream de-asserts ready; router buffers packet without loss."""
    await reset_router(dut)

    # Downstream receiver on East is NOT ready
    dut.east_out_ready.value = 0

    pkt = encode_packet(dst_x=3, dst_y=0, axon_id=0, src_x=0, src_y=0)
    dut.local_in_valid.value = 1
    dut.local_in_packet.value = pkt
    await FallingEdge(dut.clk)
    dut.local_in_valid.value = 0

    # Wait 3 cycles under backpressure: packet must hold valid and not drop
    for _ in range(3):
        await RisingEdge(dut.clk)
        assert dut.east_out_valid.value == 1
        assert int(dut.east_out_packet.value) == pkt

    # Now downstream becomes ready
    await FallingEdge(dut.clk)
    dut.east_out_ready.value = 1

    # Packet consumed on this cycle
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    await RisingEdge(dut.clk)
    # Output should now be empty (or deasserted)
    assert dut.east_out_valid.value == 0, "FIFO failed to clear after transfer"
