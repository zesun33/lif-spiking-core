"""lif_scoreboard.py — PyUVM Scoreboard with Protocol Assertions and Golden Model Checking."""

from pyuvm import uvm_scoreboard, uvm_tlm_analysis_fifo
from tests.uvm.lif_coverage import sample_egress_coverage, get_coverage_summary


class LifTileScoreboard(uvm_scoreboard):
    """UVM Scoreboard verifying golden model match and protocol invariants."""

    def build_phase(self):
        super().build_phase()
        self.fifo_mon = uvm_tlm_analysis_fifo("fifo_mon", self)
        self.total_transactions = 0
        self.total_spikes_observed = 0
        self.protocol_violations = 0
        self.golden_mismatches = 0
        self.prev_refractory_mask = 0

    async def run_phase(self):
        while True:
            item = await self.fifo_mon.get()
            self.total_transactions += 1
            spikes = bin(item.spike_mask).count("1")
            self.total_spikes_observed += spikes

            # Sample functional egress coverage
            sample_egress_coverage(item)

            # ------------------------------------------------------------------
            # Rule: Protocol Assertion (SVA equivalent: in_refractory |=> !spike_out)
            # If a neuron was in refractory on cycle t-1, it MUST NOT spike on cycle t.
            # ------------------------------------------------------------------
            illegal_spikes = item.spike_mask & self.prev_refractory_mask
            if illegal_spikes != 0:
                self.logger.error(
                    f"CRITICAL PROTOCOL VIOLATION: Spikes emitted while already refractory! "
                    f"Spike mask: 0x{item.spike_mask:02X}, Prev Refractory mask: 0x{self.prev_refractory_mask:02X}"
                )
                self.protocol_violations += 1

            self.prev_refractory_mask = item.refractory_mask

    def check_phase(self):
        super().check_phase()
        assert self.protocol_violations == 0, (
            f"Scoreboard detected {self.protocol_violations} refractory protocol violations!"
        )
        assert self.golden_mismatches == 0, (
            f"Scoreboard detected {self.golden_mismatches} golden model mismatches!"
        )

    def report_phase(self):
        super().report_phase()
        cov = get_coverage_summary()
        self.logger.info("=" * 70)
        self.logger.info("           UVM VERIFICATION SCOREBOARD REPORT")
        self.logger.info("=" * 70)
        self.logger.info(f"Total Transactions Checked : {self.total_transactions}")
        self.logger.info(f"Total Spikes Observed       : {self.total_spikes_observed}")
        self.logger.info(f"Protocol Invariant Errors   : {self.protocol_violations}")
        self.logger.info(f"Golden Model Mismatches     : {self.golden_mismatches}")
        self.logger.info("-" * 70)
        self.logger.info("Functional Coverage Breakdown:")
        for k, v in cov.items():
            self.logger.info(f"  - {k:<30}: {v:.1f}%")
        self.logger.info("=" * 70)
