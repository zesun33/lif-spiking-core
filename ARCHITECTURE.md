# lif-spiking-core: Detailed Architectural Specification

## 1. Mathematical Model
The membrane dynamics follow the discrete-time Leaky Integrate-and-Fire equation:
$$V[t] = \beta \cdot V[t-1] + \sum_{i} w_i \cdot s_i[t] - S_{\text{out}}[t-1] \cdot V_{\text{reset}}$$

Where:
- $V[t]$ is the membrane potential.
- $\beta \in (0, 1)$ is the decay factor (modeled as $1 - 2^{-\text{LEAK\_SHIFT}}$ for zero-DSP area).
- $w_i$ is the synaptic weight for input channel $i$.
- $s_i[t] \in \{0, 1\}$ is the binary input spike.
- $S_{\text{out}}[t] = \Theta(V[t] - V_{\text{th}})$ is the Heaviside step output spike.

## 2. Pinout & Interface
| Signal | Direction | Width | Description |
| :--- | :---: | :---: | :--- |
| `clk` | In | 1 | Master clock |
| `rst_n` | In | 1 | Active-low asynchronous reset |
| `spike_in_valid` | In | 1 | Strobe indicating input synaptic spikes are valid |
| `synaptic_weight` | In | 16 | Signed fixed-point synaptic input current |
| `v_threshold` | In | 16 | Signed firing threshold voltage |
| `v_reset` | In | 16 | Reset potential voltage |
| `spike_out` | Out | 1 | Single-cycle event spike pulse |
| `v_mem_out` | Out | 16 | Current membrane potential monitor |
| `in_refractory` | Out | 1 | Status flag: neuron currently in refractory dead-time |
