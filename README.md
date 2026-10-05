# lif-spiking-core

<!-- BEGIN GENERATED PROJECT GUIDE -->

## Purpose and first steps

Study and simulate LIF neuron tiles, AER routing, and a 2x2 neuromorphic mesh.

**Who it is for:** RTL and neuromorphic-computing developers studying event-driven neuron tiles and routing.

**First task:** Read the architecture, then follow the neuron/tile testbench paths and verification notes.

**What to expect:** LIF neuron/tile/router RTL, reference models, simulation tests, and recorded implementation artifacts.

**Current scope:** Implemented RTL and testbenches with historical results. Coverage is partial; implementation artifacts and timing estimates are not measurements of fabricated silicon.

**Start here:** [Architecture overview](ARCHITECTURE.md).

**Related projects:** [hw-verification-suite](https://github.com/zesun33/hw-verification-suite), [mcp-cocotb](https://github.com/zesun33/mcp-cocotb), [rust-systems-track](https://github.com/zesun33/personal-projects/tree/main/rust-systems-track).

[Choose another project](https://github.com/zesun33/personal-projects/blob/main/GETTING_STARTED.md).
<!-- END GENERATED PROJECT GUIDE -->

> Synthesizable Leaky Integrate-and-Fire (LIF) Neuromorphic Spiking Neuron Core, 8x8 Tile, 5-Port AER Router, and 4-Core 2D Mesh SoC with PyUVM verification and Nangate45 implementation artifacts.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Recorded verification: 18/18 PASS](https://img.shields.io/badge/Recorded%20verification-18%2F18%20PASS-brightgreen)](#3-recorded-verification-suite)
[![Coverage: Partial](https://img.shields.io/badge/Coverage-partial-yellow)](VERIFICATION.md)
[![Implementation: Nangate45](https://img.shields.io/badge/Implementation-Nangate45-blue)](#2-physical-design-results-nangate45)

---

## 1. Architectural Overview

`lif-spiking-core` provides synthesizable RTL and open-tool implementation artifacts of an event-driven neuromorphic compute platform scaling from individual neurons to multi-core 2D Mesh Network-on-Chip (NoC) SoCs:

```text
    ┌──────────────────────────────────────────────────────────────────┐
    │                      2x2 NEUROMORPHIC MESH SoC                   │
    │  [ Node (0, 0) ] <====== East/West ======> [ Node (1, 0) ]       │
    │        ||                                        ||              │
    │    North/South                               North/South         │
    │        ||                                        ||              │
    │  [ Node (0, 1) ] <====== East/West ======> [ Node (1, 1) ]       │
    └──────────────────────────────────────────────────────────────────┘
```

1. **LIF Neuron Primitive (`rtl/lif_neuron.v`)**:
   - 16-bit fixed-point membrane accumulator with subtractive spike reset: $V_{\text{mem}} \leftarrow V_{\text{mem}} - V_{\text{th}}$.
   - Multiplier-free shift leak (`V >> 3`) synchronized to `timestep_tick`.
   - Refractory dead-time counter and hardware saturation/hyperpolarization clamps: $V_{\text{mem}} \in [V_{\text{rest}}, +32767]$.
2. **8x8 Neuromorphic Core Tile (`rtl/lif_tile_8x8.v`)**:
   - 64 configurable signed INT8 synapses with memory-mapped SRAM readback.
   - Option 1C parallel column bitline accumulation tree + Option 1B INT8-to-INT16 sign extension.
   - Option 2B 1-cycle registered pipeline stage isolating crossbar capacitance.
3. **5-Port 2D Mesh AER NoC Router (`rtl/lif_router_2d.v`)**:
   - Single-flit 16-bit spike packets (`{dst_x[2:0], dst_y[2:0], axon_id[2:0], src_x[2:0], src_y[2:0]}`).
   - Deadlock-free Dimension-Order Routing (X → Y).
   - Round-Robin arbitration per egress port preventing packet starvation.
   - 4-entry virtual-cut-through synchronous input FIFOs with Ready/Valid handshaking.
4. **Integrated 2D Mesh Node (`rtl/lif_mesh_node_2d.v`)**:
   - Couples tile to router with automatic spike packet serialization and incoming axon decoding.
5. **4-Core 2D Neuromorphic Mesh SoC (`rtl/lif_mesh_2x2.v`)**:
   - Fully connected 2 × 2 grid with perimeter tie-offs, memory-mapped configuration demux, and per-core observability.

---

## 2. Physical Design Results (Nangate45)

The tables below retain previously reported OpenROAD/Nangate45 results. The repository contains synthesis netlists, routed DEFs, flow scripts, and layout images. These are implementation artifacts, not evidence of fabricated or measured silicon, foundry-qualified signoff, or a manufacturing tapeout.

The Fmax values are estimates computed as `1 / (10 ns - reported setup slack)` at the documented 100 MHz constraint. They are not measurements or proof that a rerun at that higher clock would close timing. The raw timing reports and tool-version manifests for these historical tables are not tracked here, so the numbers have not been independently regenerated for this documentation update. The later table's positive slack values are setup slack, not WNS (the earlier table reports WNS as zero).

OpenROAD flow scripts and Nangate45 implementation artifacts are provided for the modules below:

| Reported implementation metric | 8x8 LIF Tile (`lif_tile_8x8`) | 5-Port AER Router (`lif_router_2d`) | Notes / Standard Cell Library |
| :--- | :---: | :---: | :--- |
| **PDK Library** | `Nangate45` | `Nangate45` | FreePDK45 open standard cells |
| **Standard Cell Count** | **8,951 cells** | **1,862 cells** | Standard combinational + DFFR_X1 cells |
| **Sequential Elements** | 778 DFFs (29.1%) | 367 DFFs (50.7%) | Edge-triggered flip-flops |
| **Die Dimensions** | **197.7 × 197.7 µm** | **112.5 × 112.5 µm** | Snapped to placement tracks |
| **Core Cell Utilization** | **45.40%** | **45.82%** | Routable density without congestion |
| **Target Clock** | 100.0 MHz (10.0 ns) | 100.0 MHz (10.0 ns) | SDC clock constraints |
| **Worst Negative Slack (WNS)** | **0.00 ns** | **0.00 ns** | Zero timing violations |
| **Total Negative Slack (TNS)** | **0.00 ns** | **0.00 ns** | Fully timing-closed design |
| **Worst Setup Slack** | **+5.27 ns** | **+7.85 ns** | Positive setup timing margin |
| **Max Frequency (Fmax)** | **≈ 211.4 MHz** | **≈ 465.1 MHz** | Timing-derived estimate; not a silicon measurement |
| **Routed DEF artifact** | [`lif_tile_8x8.routed.def`](./lif_tile_8x8.routed.def) | [`lif_router_2d.routed.def`](./lif_router_2d.routed.def) | Routed physical DEF; completion is not rechecked here |

---

## 3. Recorded Verification Suite

The README records 3 regression suites totaling **18/18 passing test cases**. This is a historical summary; a fresh run of `scripts/verify.sh` exercises only the suites listed by that script and must be reported separately:

### A. 8x8 Core Tile Cocotb Suite (`tests/test_lif_tile_8x8.py`) — 8/8 PASS
1. `test_tile_config_programming_and_readback`: 64-synapse SRAM writes and registered readbacks.
2. `test_tile_column_ingress_and_pipeline_sum`: Option 1C parallel adder tree + Option 2B 1-cycle pipeline.
3. `test_tile_parallel_firing_and_subtractive_reset`: Parallel firing with subtractive voltage preservation.
4. `test_tile_refractory_recovery`: Multi-cycle dead-time countdown and recovery.
5. `test_tile_crv_poisson_profile_c_500_timesteps`: 500-timestep biological Poisson arrival sweep (210 spikes, 0 mismatches).
6. `test_tile_corner_case_positive_saturation_clamp`: +32,767 clamp without rollover.
7. `test_tile_corner_case_negative_hyperpolarization_clamp`: `V_rest = 0` floor clamp under extreme inhibition.
8. `test_tile_concurrent_config_write_hazard`: Live weight reconfiguration during streaming spikes.

### B. PyUVM Functional Cross-Coverage Suite (`tests/uvm/test_lif_tile_uvm.py`) — PASS
- **Temporal SVA Refractory Invariant**: `in_refractory |=> !neuron_spikes_out` (0 violations).
- **100% Stimulus Cross-Coverage**: `lif_cov.axon_density` (100%), `lif_cov.timestep_tick` (100%), `lif_cov.cross_stimulus_sync` (100%).

### C. 5-Port 2D Mesh AER Router Suite (`tests/test_lif_router_2d.py`) — 5/5 PASS
1. `test_router_dor_east_routing`: Horizontal East routing with DOR.
2. `test_router_dor_south_routing`: Vertical South routing with DOR.
3. `test_router_local_delivery`: Ingress packet delivery to Local tile.
4. `test_router_round_robin_fairness`: Contention arbitration between simultaneous requesters.
5. `test_router_backpressure_and_buffering`: Downstream backpressure FIFO hold without packet drop.

### D. 4-Core 2D Mesh SoC Suite (`tests/test_lif_mesh_2x2.py`) — 5/5 PASS
1. `test_mesh_config_programming_and_readback`: Memory-mapped programming of 256 synapses across 4 tiles.
2. `test_mesh_horizontal_routing_hop`: 1-hop East link spike routing: Node (0,0) → Node (1,0).
3. `test_mesh_vertical_routing_hop`: 1-hop South link spike routing: Node (0,0) → Node (0,1).
4. `test_mesh_diagonal_two_hop_cascade`: Multi-hop DOR cascade: Node (0,0) → (1,0) → (1,1).
5. `test_mesh_all_nodes_concurrent_traffic`: Simultaneous cross-diagonal spike transmission across all 4 nodes without packet loss or deadlock.

---

## 4. Quick Start

```bash
# 1. Run 8x8 Tile Cocotb Suite
pytest -v tests/test_lif_tile_8x8.py

# 2. Run PyUVM Functional Coverage Suite
pytest -v tests/uvm/test_lif_tile_uvm.py

# 3. Run AER Router Suite
pytest -v tests/test_lif_router_2d.py

# 4. Run 4-Core 2D Mesh SoC Suite
pytest -v tests/test_lif_mesh_2x2.py
```

---

## 5. Recorded Implementation Metrics (Nangate45)

Previously reported Yosys/OpenROAD results on the **Nangate45 Open Cell Library** are summarized below. The evidence limits and Fmax calculation above apply to this table too:

| Hierarchy / Design Module | Standard Cell Count | Die Dimensions (µm) | Core Area (µm²) | Utilization | Clock Target | Reported setup slack | Estimated Fmax | Routed DEF artifact |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **`lif_tile_8x8`** (Core Tile) | 8,951 | 197.7 × 197.7 | 39,085 | 45.0% | 100 MHz (10 ns) | **+5.27 ns** | **211.4 MHz** | `lif_tile_8x8.routed.def` |
| **`lif_router_2d`** (5-Port NoC Router) | 1,862 | 112.5 × 112.5 | 12,656 | 45.0% | 100 MHz (10 ns) | **+7.85 ns** | **465.1 MHz** | `lif_router_2d.routed.def` |
| **`lif_mesh_2x2`** (4-Core SoC) | 32,351 | 756.6 × 756.6 | 483,677 | 45.1% | 100 MHz (10 ns) | **+7.12 ns** | **347.2 MHz** | `lif_mesh_2x2.routed.def` |

