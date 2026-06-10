import numpy as np
import pytest

from absengine.models.scenario import RampRate, ScalarRate, VectorRate
from absengine.scenarios.expand import annual_to_monthly, expand


def test_scalar():
    assert np.allclose(expand(ScalarRate(value=0.05), 4), [0.05] * 4)


def test_vector_pads_with_last():
    assert np.allclose(expand(VectorRate(values=[0.01, 0.02]), 4), [0.01, 0.02, 0.02, 0.02])


def test_vector_truncates():
    assert np.allclose(expand(VectorRate(values=[1, 2, 3, 4, 5]), 3), [1, 2, 3])


def test_ramp():
    out = expand(RampRate(start=0.0, end=0.06, periods=4), 6)
    assert np.allclose(out, [0.0, 0.02, 0.04, 0.06, 0.06, 0.06])


def test_annual_to_monthly_roundtrip():
    smm = annual_to_monthly(np.array([0.10]))
    assert (1 - smm[0]) ** 12 == pytest.approx(0.90, abs=1e-12)
    assert annual_to_monthly(np.array([0.0]))[0] == 0.0
    assert annual_to_monthly(np.array([1.0]))[0] == 1.0
