from quant_system.portfolio.positions import build_position_book


def test_build_position_book_uses_fifo_and_prices():
    records = [
        {"symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100},
        {"symbol": "000001", "name": "Demo", "side": "BUY", "price": 12, "quantity": 100},
        {"symbol": "000001", "name": "Demo", "side": "SELL", "price": 13, "quantity": 100},
    ]

    book = build_position_book(records, cash=10000, prices={"000001": 15})

    assert len(book.positions) == 1
    assert book.positions[0].quantity == 100
    assert book.positions[0].avg_cost == 12
    assert book.positions[0].unrealized_pnl == 300
    assert book.total_exposure_pct == 0.15
