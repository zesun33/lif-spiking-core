# lif-spiking-core

> Synthesizable Leaky Integrate-and-Fire (LIF) Neuromorphic Spiking Neuron Core with Parametric Decay and Refractory Guard.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Framework: snnTorch](https://img.shields.io/badge/framework-snnTorch%20%7C%20SpikingJelly-purple)](https://github.com/jeshraghian/snntorch)
[![EDA: OpenROAD & Yosys](https://img.shields.io/badge/EDA-OpenROAD%20%7C%20Yosys-brightgreen)](#)

## Overview
`lif-spiking-core` is a hardware-accelerated, synthesizable silicon implementation of the Leaky Integrate-and-Fire (LIF) neuron model, the foundational computational primitive in Spiking Neural Networks (SNNs). Designed for energy-efficient, event-driven temporal processing.

## Architecture
- **Membrane Potential ($V_{\text{mem}}$)**: 16-bit signed fixed-point state accumulator with saturation protection.
- **Parametric Leaky Decay**: Shift-based multiplier-free leak ($\beta = 1 - 2^{-k}$) or fixed-point factor.
- **Configurable Reset Schema**: Subtractive ($V_{\text{mem}} \leftarrow V_{\text{mem}} - V_{\text{th}}$) or Hard Reset ($V_{\text{mem}} \leftarrow V_{\text{reset}}$).
- **Refractory Period**: Configurable dead-time counter suppressing spurious firing after an output event.

## Verification & Toolchain
- **RTL Lint & AST Review**: `mcp-rtl-review` + `mcp-verilog`
- **Co-Simulation**: `mcp-cocotb` testbench driving Poisson spike trains vs `snnTorch` golden model.
- **Silicon Synthesis & P&R**: `mcp-yosys` + `mcp-openroad` through `agentic-asic`.
- **GPU Baseline**: SNN batch kernel profiled in `kernel-forge`.
