from pathlib import Path

from quant_trading.utils.config import load_research_config


def test_repository_research_config_is_valid() -> None:
    config = load_research_config(Path("config/research.yaml"))
    assert config.data.auto_adjust is True
    assert 0 < config.validation.max_abs_daily_return < 1
    assert config.features.primary_target == "target_return_5d"
    assert config.features.market_benchmark == "SPY"
    assert config.signal_research.primary_target == "target_return_5d"
    assert config.signal_research.hac_lags == 4
    assert all(not item.name.startswith("target_") for item in config.signal_research.candidates)
