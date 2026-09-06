# lif-spiking-core

> Synthesizable Leaky Integrate-and-Fire (LIF) Neuromorphic Spiking Neuron Core & 8x8 Tile with Industrial PyUVM Verification and Nangate45 ASIC Tapeout.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Verification: PyUVM & Cocotb](https://img.shields.io/badge/Verification-PyUVM%20%2B%20Cocotb%20PASS-brightgreen)](#industrial-verification-suite)
[![Coverage: 100% Stimulus](https://img.shields.io/badge/Coverage-100%25%20Stimulus%20Cross-brightgreen)](#functional-cross-coverage)
[![ASIC: Nangate45 211MHz](https://img.shields.io/badge/ASIC-Nangate45%20%7C%20211%20MHz-blue)](#physical-design--silicon-tapeout)

---

## 1. Architectural Overview

`lif-spiking-core` is an industrial-grade, fully synthesizable silicon implementation of an $8 \times 8$ Neuromorphic Spiking Core Tile (`lif_tile_8x8.v`) driving 8 parallel Leaky Integrate-and-Fire (LIF) neurons (`lif_neuron.v`) across 64 configurable synaptic weights:

- **Synaptic Storage & Addressing**: $8 \times 8$ crossbar matrix of signed INT8 weights ($-128 \dots +127$) accessible via synchronous SRAM configuration port (`cfg_we`, `cfg_addr`, `cfg_wdata`, `cfg_rdata`) with 1-cycle readback latency.
- **Compute-in-Memory Accumulation (Option 1C)**: Fully parallel column adder trees summing activated synaptic weights instantaneously across all 8 axon rows.
- **Precision Staging (Option 1B)**: Synaptic weights expand from INT8 to INT16 sign-extended membrane precision during accumulation to eliminate quantization overflow.
- **Registered Pipeline Staging (Option 2B)**: 1-cycle synchronous pipeline register between column accumulation and neuron membrane integration, isolating crossbar capacitance and achieving high clock frequencies.
- **Parametric Shift-Leak Decay**: Multiplier-free membrane leakage ($V_{\text{mem}} \leftarrow V_{\text{mem}} - (V_{\text{mem}} \gg 3)$) synchronized to the global `timestep_tick` pulse.
- **Subtractive Spike Reset**: When $V_{\text{mem}} \ge V_{\text{th}}$, the neuron fires an action potential pulse and subtracts threshold ($V_{\text{mem}} \leftarrow V_{\text{mem}} - V_{\text{th}}$), preserving residual membrane charge.
- **Refractory Dead-Time Protection**: Hardware counter suppressing action potential generation for $N$ timesteps post-firing.
- **Saturation & Hyperpolarization Clamps**: Hardware guards bounding $V_{\text{mem}} \in [V_{\text{rest}}, +32767]$.

---

## 2. Physical Design & Silicon Tapeout (Nangate45)

The design has been compiled, floorplanned, placed, routed, and timed using **OpenROAD** on the **Nangate45** open-cell library:

| Silicon Metric | Sign-off Value | Notes / Description |
| :--- | :---: | :--- |
| **PDK / Standard Cell Library** | `Nangate45` | Open-source 45nm standard cell PDK |
| **Top-Level Module** | `lif_tile_8x8` | Complete 64-synapse $8 \times 8$ core tile |
| **Total Standard Cells** | **8,951** | Combinational gates + 778 D-flip-flops (`DFFR_X1`) |
| **Sequential Gate Area** | $4,138.96 \ \mu\text{m}^2$ | 29.12% of total cell area |
| **Total Cell Area** | $14,212.91 \ \mu\text{m}^2$ | Pure gate silicon footprint |
| **Die Dimensions** | **$197.7 \times 197.7 \ \mu\text{m}$** | Die area: $39,085 \ \mu\text{m}^2$ |
| **Core Cell Utilization** | **$45.40\%$** | Optimal routability without congestion |
| **Target Clock Frequency** | **$100.0\text{ MHz}$** | Target clock period: $10.0\text{ ns}$ |
| **Worst Negative Slack (WNS)** | **$0.00\text{ ns}$** | Zero setup violations |
| **Total Negative Slack (TNS)** | **$0.00\text{ ns}$** | Fully timing-closed design |
| **Worst Setup Slack** | **$+5.27\text{ ns}$** | **Maximum Fmax: $\approx 211.4\text{ MHz}$** |
| **Tapeout Netlist & DEF** | [`lif_tile_8x8.routed.def`](./lif_tile_8x8.routed.def) | 1.3 MB routed physical design DEF |

---

## 3. Industrial Verification Suite

The verification environment combines two complementary test methodologies:

### A. Cocotb Verification Suite (`tests/test_lif_tile_8x8.py`)
- **8/8 Testcases Passing** in 0.18 seconds:
  1. `test_tile_config_programming_and_readback`: Full 64-synapse SRAM write and registered readback verification.
  2. `test_tile_column_ingress_and_pipeline_sum`: Verification of Option 1C adder tree and Option 2B 1-cycle pipeline register.
  3. `test_tile_parallel_firing_and_subtractive_reset`: Parallel firing of all 8 neurons with subtractive reset residual preservation.
  4. `test_tile_refractory_recovery`: Verification of refractory dead-time countdown and recovery.
  5. `test_tile_crv_poisson_profile_c_500_timesteps`: 500-timestep biological Poisson arrival sweep (sparsity 10% $\to$ 90%, 210 output spikes, 0 golden mismatches).
  6. `test_tile_corner_case_positive_saturation_clamp`: Clamping at $+32767$ without rollover overflow.
  7. `test_tile_corner_case_negative_hyperpolarization_clamp`: Clamping at $V_{\text{rest}} = 0$ under extreme inhibitory current.
  8. `test_tile_concurrent_config_write_hazard`: Live weight reconfiguration during streaming axon spike traffic.

### B. IEEE 1800.2 PyUVM Suite (`tests/uvm/test_lif_tile_uvm.py`)
- **Phased Hierarchy**: `build_phase` $\to$ `connect_phase` $\to$ `run_phase` $\to$ `check_phase` $\to$ `report_phase`.
- **Decoupled Architecture**: Abstract sequence items driven through a synchronous BFM (`LifTileDriver`), monitored by a passive observer (`LifTileMonitor`), and verified in a scoreboard (`LifTileScoreboard`) via non-blocking TLM analysis FIFOs.
- **Temporal SVA Protocol Assertion**:
  $$\text{in\_refractory} \mathrel{\mathtt{|=>}} !\text{neuron\_spikes\_out}$$
  Enforced across all clock cycles to prove that no neuron emits spurious action potentials during dead-time refractory states.
- **Functional Cross-Coverage (`cocotb-coverage`)**:
  - `lif_cov.axon_density`: **100.0%**
  - `lif_cov.timestep_tick`: **100.0%**
  - `lif_cov.cross_stimulus_sync`: **100.0%**
  - `lif_cov.spike_count`: **60.0%**
  - `lif_cov.refractory_count`: **75.0%**

---

## 4. Quick Start & Reproduction

### Prerequisites
Run using rootless Podman with our pre-packaged EDA images:
- Simulator: `localhost/zesun33/verilog` (Icarus Verilog 12.0, Cocotb 2.1.0, PyUVM 5.0.0, cocotb-coverage 2.0)
- Synthesis & Physical Design: `localhost/zesun33/asic` (Yosys 0.38, OpenROAD 2.0, OpenSTA 2.5)

### Running Verification
```bash
# 1. Run full 8/8 Cocotb regression suite
pytest -v tests/test_lif_tile_8x8.py

# 2. Run PyUVM functional cross-coverage suite
pytest -v tests/uvm/test_lif_tile_uvm.py
```

### Running Physical Design
```bash
# Re-synthesize gate-level netlist with Yosys
yosys << 'EOF'
read_verilog -sv rtl/lif_neuron.v
read_verilog -sv rtl/lif_tile_8x8.v
hierarchy -check -top lif_tile_8x8
synth -top lif_tile_8x8 -flatten
dfflibmap -liberty /opt/platforms/nangate45/NangateOpenCellLibrary_typical.lib
abc -liberty /opt/platforms/nangate45/NangateOpenCellLibrary_typical.lib
clean
write_verilog -noattr lif_tile_8x8.gate.v
EOF

# Execute OpenROAD Placement, Routing, and STA
openroad run_pnr.tcl
```
