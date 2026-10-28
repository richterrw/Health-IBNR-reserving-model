import numpy as np
import pandas as pd
import pytest

from ibnr import methods

# Taylor & Ashe (1983) cumulative triangle, as used by Mack (1993) and the R
# ChainLadder package's GenIns data set.
GENINS = [
    [357848, 1124788, 1735330, 2218270, 2745596, 3319994, 3466336, 3606286, 3833515, 3901463],
    [352118, 1236139, 2170033, 3353322, 3799067, 4120063, 4647867, 4914039, 5339085],
    [290507, 1292306, 2218525, 3235179, 3985995, 4132918, 4628910, 4909315],
    [310608, 1418858, 2195047, 3757447, 4029929, 4381982, 4588268],
    [443160, 1136350, 2128333, 2897821, 3402672, 3873311],
    [396132, 1333217, 2180715, 2985752, 3691712],
    [440832, 1288463, 2419861, 3483130],
    [359480, 1421128, 2864498],
    [376686, 1363294],
    [344014],
]


@pytest.fixture
def genins() -> pd.DataFrame:
    n = len(GENINS)
    return pd.DataFrame([r + [np.nan] * (n - len(r)) for r in GENINS], columns=range(n), dtype=float)


def test_chain_ladder_matches_published_reserve(genins):
    f = methods.select_volume_weighted(genins, None, max_lag=99)
    assert f[0] == pytest.approx(3.4906, abs=1e-4)
    out = methods.mack(genins, f, max_lag=99)
    assert out.loc["Total", "reserve"] == pytest.approx(18_680_856, rel=1e-6)


def test_mack_standard_error_matches_published(genins):
    f = methods.select_volume_weighted(genins, None, max_lag=99)
    out = methods.mack(genins, f, max_lag=99)
    # R ChainLadder::MackChainLadder(GenIns): total Mack S.E. 2,447,095
    assert out.loc["Total", "se"] == pytest.approx(2_447_095, rel=1e-4)
    # Most recent year: reserve 4,625,811, S.E. 1,363,155
    assert out.loc[9, "reserve"] == pytest.approx(4_625_811, rel=1e-5)
    assert out.loc[9, "se"] == pytest.approx(1_363_155, rel=1e-4)


def test_completion_factor_is_inverse_cdf(genins):
    f = methods.select_volume_weighted(genins, None, max_lag=99)
    cf = methods.completion_factors(f, genins.shape[1])
    assert cf.iloc[-1] == 1.0
    assert cf[0] == pytest.approx(1 / np.prod(f.to_numpy()))
    paid = genins.ffill(axis=1).iloc[:, -1]
    age = genins.notna().sum(axis=1) - 1
    ult_cf = (paid / cf.reindex(age).to_numpy()).sum()
    assert ult_cf - paid.sum() == pytest.approx(18_680_856, rel=1e-6)


def test_straight_average_drops_high_and_low():
    lr = pd.DataFrame({0: [1.0, 5.0, 2.0, 3.0, 4.0, 100.0, 0.5]})
    sel = methods.select_straight_average(lr, n_months=6, exclude_hi_lo=True, max_lag=36)
    # last six: 5, 2, 3, 4, 100, 0.5 -> drop 100 and 0.5
    assert sel[0] == pytest.approx(3.5)
    assert methods.select_straight_average(lr, 6, True, max_lag=0)[0] == 1.0


def test_lognormal_percentile():
    assert methods.lognormal_percentile(100, 0, 0.95) == 100
    p50 = methods.lognormal_percentile(100, 10, 0.5)
    assert p50 < 100 < methods.lognormal_percentile(100, 10, 0.75)
