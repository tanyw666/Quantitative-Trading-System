from quant_system.cli import build_parser, records_from_selection


def test_dragon_screen_parser_sets_subcommand():
    args = build_parser().parse_args(
        ["dragon", "screen", "--csv", "data/sample_ohlcv.csv", "--top", "3", "--entry-gate", "pass"]
    )

    assert args.command == "dragon"
    assert args.dragon_command == "screen"
    assert args.top == 3
    assert args.entry_gate == "pass"


def test_dragon_check_parser_sets_symbol():
    args = build_parser().parse_args(["dragon", "check", "--csv", "data/sample_ohlcv.csv", "--symbol", "1"])

    assert args.command == "dragon"
    assert args.dragon_command == "check"
    assert args.symbol == "1"


def test_records_from_selection_keeps_dragon_metadata():
    records = records_from_selection(
        "dragon_leader",
        [
            {
                "date": "2024-01-25",
                "symbol": "000001",
                "name": "Dragon",
                "close": 12.1,
                "reason": "demo",
                "entry_gate": "pass",
                "dragon_state": "sealed",
                "dragon_tags": "reseal-candidate",
                "dragon_score": 118,
                "seal_quality_score": 100,
            }
        ],
    )

    assert records[0].entry_gate == "pass"
    assert records[0].dragon_tags == "reseal-candidate"
    assert records[0].dragon_score == 118
