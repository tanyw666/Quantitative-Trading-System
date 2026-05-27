from quant_system.portfolio.positions import build_position_book
from quant_system.portfolio.risk_check import check_holding_risk


def test_holding_risk_blocks_stop_loss():
    records = [{"symbol": "000001", "side": "BUY", "price": 10, "quantity": 100}]
    book = build_position_book(records, cash=10000, prices={"000001": 9})

    report = check_holding_risk(book, stops={"000001": 9.5})

    assert report.status == "block"
    assert any(check.name == "stop_loss" and check.status == "block" for check in report.checks)


def test_holding_risk_warns_when_price_missing():
    records = [{"symbol": "000001", "side": "BUY", "price": 10, "quantity": 100}]
    book = build_position_book(records, cash=10000, prices={})

    report = check_holding_risk(book)

    assert report.status == "warn"
