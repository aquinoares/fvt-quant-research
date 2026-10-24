import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))

from dsr import (  # noqa: E402
    deflated_sharpe_ratio,
    expected_max_sharpe_z,
    max_sharpe_bound,
    norm_cdf,
    sharpe_standard_error,
)


def test_norm_cdf_known_values():
    assert abs(norm_cdf(0.0) - 0.5) < 1e-12
    assert abs(norm_cdf(1.959963984540054) - 0.975) < 1e-9
    assert abs(norm_cdf(-1.959963984540054) - 0.025) < 1e-9


def test_gumbel_anchor_from_paper():
    assert abs(expected_max_sharpe_z(100) - 2.366) < 0.001
    assert abs(max_sharpe_bound(100, 1000) - 0.0749) < 0.001


def test_m1_identity_is_plain_t_statistic():
    dsr, p = deflated_sharpe_ratio(1.0, 1, 252)
    assert abs(dsr - 1.0 / math.sqrt(1.5 / 251)) < 1e-9
    assert p < 1e-6


def test_at_expected_max_p_is_half():
    sr_max = max_sharpe_bound(100, 1000)
    dsr, p = deflated_sharpe_ratio(sr_max, 100, 1000)
    assert abs(dsr) < 1e-12
    assert abs(p - 0.5) < 1e-9


def test_more_trials_means_less_significance():
    ps = [deflated_sharpe_ratio(0.5, m, 252)[1] for m in (1, 10, 100, 1000, 10000)]
    assert all(a < b for a, b in zip(ps, ps[1:]))


def test_fat_tails_penalize():
    normal = deflated_sharpe_ratio(1.0, 50, 252, skewness=0.0, kurtosis=3.0)[0]
    fat = deflated_sharpe_ratio(1.0, 50, 252, skewness=-2.0, kurtosis=9.0)[0]
    assert fat < normal


def test_paper_core_claim_sr02_m200_not_significant():
    _, p = deflated_sharpe_ratio(0.2, 200, 252)
    assert p > 0.05


def test_observed_below_bound_is_not_significant():
    _, p = deflated_sharpe_ratio(0.0, 100, 1000)
    assert p > 0.9


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(1.0, 0, 252)
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(1.0, 10, 1)
