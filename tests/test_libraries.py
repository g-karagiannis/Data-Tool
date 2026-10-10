"""The modelling libraries the Workshop offers run on our pandas version and agree with
each other on data whose true answer is known (slope = 2 within entities)."""
import warnings

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n_entities, n_periods = 30, 40
    entity = np.repeat(np.arange(n_entities), n_periods)
    period = np.tile(np.arange(n_periods), n_entities)
    effect = rng.normal(0, 3, n_entities)[entity]
    x = rng.normal(0, 1, entity.size) + 0.5 * effect
    y = 2.0 * x + effect + rng.normal(0, 1, entity.size)
    return pd.DataFrame({"entity": entity, "period": period, "x": x, "y": y})


def test_statsmodels_ols_with_entity_dummies(panel):
    import statsmodels.formula.api as smf

    fit = smf.ols("y ~ x + C(entity)", data=panel).fit()
    assert fit.params["x"] == pytest.approx(2.0, abs=0.1)


def test_statsmodels_time_series_forecast():
    from statsmodels.tsa.arima.model import ARIMA

    series = pd.Series(np.cumsum(np.random.default_rng(1).normal(0, 1, 120)) + 50,
                       index=pd.date_range("2025-01-01", periods=120, freq="B"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        forecast = ARIMA(series, order=(1, 1, 0)).fit().forecast(5)
    assert len(forecast) == 5 and forecast.notna().all()


def test_linearmodels_and_pyfixest_fixed_effects_agree(panel):
    import pyfixest as pf
    from linearmodels.panel import PanelOLS

    lm = PanelOLS.from_formula("y ~ x + EntityEffects", data=panel.set_index(["entity", "period"])).fit()
    pf_fit = pf.feols("y ~ x | entity", data=panel)
    assert lm.params["x"] == pytest.approx(2.0, abs=0.1)
    assert pf_fit.coef()["x"] == pytest.approx(lm.params["x"], abs=1e-8)


def test_arch_still_available():
    from arch import arch_model  # noqa: F401
