import pandas as pd

from quant_system.data.universe_builder import UniverseBuildOptions, filter_universe, infer_board, infer_market, normalize_universe


def test_infer_market_and_board():
    assert infer_market("600000") == "SH"
    assert infer_market("000001") == "SZ"
    assert infer_market("830000") == "BJ"
    assert infer_board("688001") == "STAR"
    assert infer_board("300001") == "CHINEXT"


def test_filter_universe_excludes_st_bj_and_optional_boards():
    raw = pd.DataFrame(
        {
            "代码": ["000001", "300001", "688001", "830000", "600001"],
            "名称": ["平安银行", "创业板股", "科创板股", "北交所股", "ST样例"],
        }
    )

    filtered = filter_universe(
        normalize_universe(raw),
        UniverseBuildOptions(include_st=False, include_bj=False, include_star=False, include_chinext=False),
    )

    assert filtered["symbol"].tolist() == ["000001"]
