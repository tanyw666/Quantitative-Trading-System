from pathlib import Path

from quant_system.cli import build_parser


def test_portfolio_allocate_accepts_constraint_audit_args():
    args = build_parser().parse_args(
        [
            "portfolio",
            "allocate",
            "--csv",
            "prices.csv",
            "--sqlite",
            "quant.sqlite",
            "--constraint-log",
            "constraints.jsonl",
        ]
    )

    assert args.sqlite == Path("quant.sqlite")
    assert args.constraint_log == Path("constraints.jsonl")


def test_portfolio_precheck_accepts_constraint_audit_args():
    args = build_parser().parse_args(
        [
            "portfolio",
            "precheck",
            "--csv",
            "prices.csv",
            "--symbol",
            "000001",
            "--entry-price",
            "10",
            "--planned-pct",
            "0.1",
            "--sqlite",
            "quant.sqlite",
            "--constraint-log",
            "constraints.jsonl",
        ]
    )

    assert args.sqlite == Path("quant.sqlite")
    assert args.constraint_log == Path("constraints.jsonl")


def test_portfolio_precheck_accepts_format_arg():
    args = build_parser().parse_args(
        [
            "portfolio",
            "precheck",
            "--csv",
            "prices.csv",
            "--symbol",
            "000001",
            "--entry-price",
            "10",
            "--planned-pct",
            "0.1",
            "--format",
            "markdown",
        ]
    )

    assert args.format == "markdown"


def test_report_weekly_accepts_constraint_log_arg():
    args = build_parser().parse_args(
        [
            "report",
            "weekly",
            "--constraint-log",
            "constraints.jsonl",
        ]
    )

    assert args.constraint_log == Path("constraints.jsonl")


def test_report_daily_accepts_constraint_log_arg():
    args = build_parser().parse_args(
        [
            "report",
            "daily",
            "--constraint-log",
            "constraints.jsonl",
        ]
    )

    assert args.constraint_log == Path("constraints.jsonl")


def test_report_briefing_accepts_constraint_log_arg():
    args = build_parser().parse_args(
        [
            "report",
            "briefing",
            "--csv",
            "prices.csv",
            "--constraint-log",
            "constraints.jsonl",
        ]
    )

    assert args.constraint_log == Path("constraints.jsonl")


def test_review_trade_add_accepts_workflow_gate_args():
    args = build_parser().parse_args(
        [
            "review",
            "trade-add",
            "--date",
            "2026-05-29",
            "--symbol",
            "000001",
            "--side",
            "BUY",
            "--price",
            "10",
            "--quantity",
            "100",
            "--reason",
            "test",
            "--workflow-summary",
            "reports/premarket_workflow.json",
            "--gate-status",
            "warn",
            "--gate-reason",
            "数据健康存在预警",
        ]
    )

    assert args.workflow_summary == Path("reports/premarket_workflow.json")
    assert args.gate_status == "warn"
    assert args.gate_reason == ["数据健康存在预警"]
