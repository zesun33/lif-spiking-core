"""lif_coverage.py — Functional Cross-Coverage Collector using cocotb-coverage."""

from cocotb_coverage.coverage import CoverPoint, CoverCross, coverage_db


# ------------------------------------------------------------------------------
# CoverPoints & Crosses for Stimulus & Configuration
# ------------------------------------------------------------------------------
@CoverPoint(
    "lif_cov.axon_density",
    xf=lambda item: bin(item.spike_vector).count("1"),
    bins=[0, 1, 2, 4, 8]
)
@CoverPoint(
    "lif_cov.timestep_tick",
    xf=lambda item: item.timestep_tick,
    bins=[0, 1]
)
@CoverCross(
    "lif_cov.cross_stimulus_sync",
    items=["lif_cov.axon_density", "lif_cov.timestep_tick"]
)
def sample_stimulus_coverage(item):
    """Sample stimulus transaction into coverage model."""
    pass


# ------------------------------------------------------------------------------
# CoverPoints & Crosses for Egress & Invariants
# ------------------------------------------------------------------------------
@CoverPoint(
    "lif_cov.spike_count",
    xf=lambda item: bin(item.spike_mask).count("1"),
    bins=[0, 1, 2, 4, 8]
)
@CoverPoint(
    "lif_cov.refractory_count",
    xf=lambda item: bin(item.refractory_mask).count("1"),
    bins=[0, 1, 4, 8]
)
@CoverCross(
    "lif_cov.cross_output_state",
    items=["lif_cov.spike_count", "lif_cov.refractory_count"]
)
def sample_egress_coverage(item):
    """Sample monitored egress transaction into coverage model."""
    pass


def get_coverage_summary():
    """Returns structured coverage statistics across all defined CoverPoints and Crosses."""
    details = {}
    for name in [
        "lif_cov.axon_density",
        "lif_cov.timestep_tick",
        "lif_cov.cross_stimulus_sync",
        "lif_cov.spike_count",
        "lif_cov.refractory_count",
        "lif_cov.cross_output_state"
    ]:
        cov_obj = coverage_db.get(name)
        if cov_obj is not None:
            details[name] = cov_obj.cover_percentage
        else:
            details[name] = 0.0

    return details
