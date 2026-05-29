from pathlib import Path

from quant_system.cli import build_parser


def test_portfolio_exit_plan_accepts_sell_plan_args():
    args = build_parser().parse_args(
        [
            "portfolio",
            "exit-plan",
            "--journal",
            "trades.jsonl",
            "--price",
            "000001=10",
            "--stop",
            "000001=9",
            "--target",
            "000001=12",
            "--invalidate",
            "000002=leader failed",
            "--record",
        ]
    )

    assert args.portfolio_command == "exit-plan"
    assert args.target == ["000001=12"]
    assert args.invalidate == ["000002=leader failed"]
    assert args.record is True
    assert args.lot_level is False


def test_portfolio_exit_plan_accepts_lot_level_flag():
    args = build_parser().parse_args(
        [
            "portfolio",
            "exit-plan",
            "--journal",
            "trades.jsonl",
            "--lot-level",
        ]
    )

    assert args.portfolio_command == "exit-plan"
    assert args.lot_level is True


def test_review_exit_audit_accepts_args():
    args = build_parser().parse_args(
        [
            "review",
            "exit-audit",
            "--exit-log",
            "exit_plans.jsonl",
            "--trade-log",
            "trades.jsonl",
            "--format",
            "markdown",
        ]
    )

    assert args.review_command == "exit-audit"
    assert args.exit_log == Path("exit_plans.jsonl")
    assert args.trade_log == Path("trades.jsonl")
    assert args.format == "markdown"


def test_review_lot_exit_audit_accepts_args():
    args = build_parser().parse_args(
        [
            "review",
            "lot-exit-audit",
            "--exit-log",
            "exit_plans.jsonl",
            "--trade-log",
            "trades.jsonl",
            "--format",
            "markdown",
        ]
    )

    assert args.review_command == "lot-exit-audit"
    assert args.exit_log == Path("exit_plans.jsonl")
    assert args.trade_log == Path("trades.jsonl")
    assert args.format == "markdown"


def test_portfolio_lifecycle_accepts_args():
    args = build_parser().parse_args(
        [
            "portfolio",
            "lifecycle",
            "--journal",
            "trades.jsonl",
            "--trade-plan-log",
            "trade_plans.jsonl",
            "--action-log",
            "position_actions.jsonl",
            "--exit-log",
            "exit_plans.jsonl",
            "--format",
            "markdown",
        ]
    )

    assert args.portfolio_command == "lifecycle"
    assert args.trade_plan_log == Path("trade_plans.jsonl")
    assert args.format == "markdown"


def test_review_lifecycle_accepts_args():
    args = build_parser().parse_args(
        [
            "review",
            "lifecycle",
            "--journal",
            "trades.jsonl",
            "--trade-plan-log",
            "trade_plans.jsonl",
            "--format",
            "markdown",
        ]
    )

    assert args.review_command == "lifecycle"
    assert args.trade_plan_log == Path("trade_plans.jsonl")
    assert args.format == "markdown"
