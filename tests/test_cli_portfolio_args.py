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


def test_portfolio_confirm_accepts_execution_confirmation_args():
    args = build_parser().parse_args(
        [
            "portfolio",
            "confirm",
            "--csv",
            "prices.csv",
            "--symbol",
            "000001",
            "--current-price",
            "10.2",
            "--planned-pct",
            "0.1",
            "--battle-plan",
            "battle_plan.json",
            "--reference-price",
            "10",
            "--warn-scale",
            "0.4",
            "--format",
            "markdown",
            "--output",
            "confirm.md",
        ]
    )

    assert args.portfolio_command == "confirm"
    assert args.current_price == 10.2
    assert args.battle_plan == Path("battle_plan.json")
    assert args.reference_price == 10
    assert args.warn_scale == 0.4
    assert args.output == Path("confirm.md")


def test_portfolio_confirm_accepts_record_log_args():
    args = build_parser().parse_args(
        [
            "portfolio",
            "confirm",
            "--csv",
            "prices.csv",
            "--symbol",
            "000001",
            "--current-price",
            "10",
            "--planned-pct",
            "0.1",
            "--record",
            "--log",
            "execution_confirms.jsonl",
        ]
    )

    assert args.record is True
    assert args.log == Path("execution_confirms.jsonl")


def test_portfolio_tradable_accepts_hard_gate_args():
    args = build_parser().parse_args(
        [
            "portfolio",
            "tradable",
            "--csv",
            "prices.csv",
            "--symbol",
            "000001",
            "--current-price",
            "10.2",
            "--planned-pct",
            "0.1",
            "--stop-price",
            "9.5",
            "--target-price",
            "12",
            "--as-of",
            "2026-05-30",
            "--max-stale-days",
            "2",
            "--limit-buffer-pct",
            "0.003",
            "--format",
            "markdown",
        ]
    )

    assert args.portfolio_command == "tradable"
    assert args.current_price == 10.2
    assert args.stop_price == 9.5
    assert args.max_stale_days == 2
    assert args.limit_buffer_pct == 0.003
    assert args.format == "markdown"


def test_portfolio_approve_accepts_final_approval_args():
    args = build_parser().parse_args(
        [
            "portfolio",
            "approve",
            "--csv",
            "prices.csv",
            "--symbol",
            "000001",
            "--current-price",
            "10.2",
            "--planned-pct",
            "0.1",
            "--assistant-json",
            "assistant.json",
            "--battle-plan",
            "battle_plan.json",
            "--pretrade-json",
            "pretrade.json",
            "--execution-confirm",
            "confirm.json",
            "--record",
            "--log",
            "order_approvals.jsonl",
            "--sqlite",
            "quant.sqlite",
            "--format",
            "markdown",
        ]
    )

    assert args.portfolio_command == "approve"
    assert args.assistant_json == Path("assistant.json")
    assert args.battle_plan == Path("battle_plan.json")
    assert args.pretrade_json == Path("pretrade.json")
    assert args.execution_confirm == Path("confirm.json")
    assert args.log == Path("order_approvals.jsonl")
    assert args.sqlite == Path("quant.sqlite")
    assert args.record is True


def test_review_approvals_accepts_history_args():
    args = build_parser().parse_args(
        [
            "review",
            "approvals",
            "--log",
            "order_approvals.jsonl",
            "--sqlite",
            "quant.sqlite",
            "--symbol",
            "000001",
            "--status",
            "warn",
            "--limit",
            "5",
            "--format",
            "markdown",
        ]
    )

    assert args.review_command == "approvals"
    assert args.log == Path("order_approvals.jsonl")
    assert args.sqlite == Path("quant.sqlite")
    assert args.symbol == "000001"
    assert args.status == "warn"
    assert args.limit == 5
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


def test_report_battle_plan_accepts_output_and_format_args():
    args = build_parser().parse_args(
        [
            "report",
            "battle-plan",
            "--csv",
            "prices.csv",
            "--format",
            "json",
            "--output",
            "battle_plan.json",
        ]
    )

    assert args.report_command == "battle-plan"
    assert args.format == "json"
    assert args.output == Path("battle_plan.json")


def test_report_cockpit_accepts_execution_audit_args():
    args = build_parser().parse_args(
        [
            "report",
            "cockpit",
            "--csv",
            "prices.csv",
            "--confirm-log",
            "execution_confirms.jsonl",
            "--journal",
            "trades.jsonl",
            "--lookahead-days",
            "2",
            "--format",
            "json",
            "--output",
            "cockpit.json",
        ]
    )

    assert args.report_command == "cockpit"
    assert args.confirm_log == Path("execution_confirms.jsonl")
    assert args.journal == Path("trades.jsonl")
    assert args.lookahead_days == 2
    assert args.format == "json"
    assert args.output == Path("cockpit.json")


def test_report_timeline_accepts_phase_args():
    args = build_parser().parse_args(
        [
            "report",
            "timeline",
            "--csv",
            "prices.csv",
            "--confirm-log",
            "execution_confirms.jsonl",
            "--journal",
            "trades.jsonl",
            "--as-of",
            "2026-05-30T10:00:00",
            "--format",
            "json",
            "--output",
            "timeline.json",
            "--record-state",
            "--state-log",
            "timeline_states.jsonl",
        ]
    )

    assert args.report_command == "timeline"
    assert args.confirm_log == Path("execution_confirms.jsonl")
    assert args.as_of == "2026-05-30T10:00:00"
    assert args.output == Path("timeline.json")
    assert args.record_state is True
    assert args.state_log == Path("timeline_states.jsonl")


def test_report_assistant_accepts_unified_panel_args():
    args = build_parser().parse_args(
        [
            "report",
            "assistant",
            "--csv",
            "prices.csv",
            "--confirm-log",
            "execution_confirms.jsonl",
            "--state-log",
            "timeline_states.jsonl",
            "--as-of",
            "2026-05-30T10:00:00",
            "--repeat-threshold",
            "3",
            "--stale-days",
            "2",
            "--format",
            "json",
            "--output",
            "assistant.json",
        ]
    )

    assert args.report_command == "assistant"
    assert args.confirm_log == Path("execution_confirms.jsonl")
    assert args.state_log == Path("timeline_states.jsonl")
    assert args.repeat_threshold == 3
    assert args.stale_days == 2
    assert args.output == Path("assistant.json")


def test_review_execution_audit_accepts_confirm_log_args():
    args = build_parser().parse_args(
        [
            "review",
            "execution-audit",
            "--confirm-log",
            "execution_confirms.jsonl",
            "--trade-log",
            "trades.jsonl",
            "--lookahead-days",
            "2",
            "--format",
            "markdown",
        ]
    )

    assert args.review_command == "execution-audit"
    assert args.confirm_log == Path("execution_confirms.jsonl")
    assert args.trade_log == Path("trades.jsonl")
    assert args.lookahead_days == 2
    assert args.format == "markdown"


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
            "--order-approval",
            "approval.json",
            "--gate-status",
            "warn",
            "--gate-reason",
            "data_health_warning",
        ]
    )

    assert args.workflow_summary == Path("reports/premarket_workflow.json")
    assert args.gate_status == "warn"
    assert args.gate_reason == ["data_health_warning"]
    assert args.order_approval == Path("approval.json")


def test_review_approval_audit_accepts_args():
    args = build_parser().parse_args(
        [
            "review",
            "approval-audit",
            "--approval-log",
            "order_approvals.jsonl",
            "--trade-log",
            "trades.jsonl",
            "--sqlite",
            "quant.sqlite",
            "--lookahead-days",
            "2",
            "--value-tolerance-pct",
            "0.03",
            "--format",
            "markdown",
        ]
    )

    assert args.review_command == "approval-audit"
    assert args.approval_log == Path("order_approvals.jsonl")
    assert args.trade_log == Path("trades.jsonl")
    assert args.sqlite == Path("quant.sqlite")
    assert args.lookahead_days == 2
    assert args.value_tolerance_pct == 0.03
    assert args.format == "markdown"


def test_review_approval_cooldown_accepts_args():
    args = build_parser().parse_args(
        [
            "review",
            "approval-cooldown",
            "--approval-log",
            "order_approvals.jsonl",
            "--trade-log",
            "trades.jsonl",
            "--sqlite",
            "quant.sqlite",
            "--constraint-log",
            "constraints.jsonl",
            "--block-threshold",
            "1",
            "--warn-threshold",
            "3",
            "--fallback-threshold",
            "2",
            "--warn-exposure-multiplier",
            "0.4",
            "--record",
            "--format",
            "markdown",
        ]
    )

    assert args.review_command == "approval-cooldown"
    assert args.approval_log == Path("order_approvals.jsonl")
    assert args.trade_log == Path("trades.jsonl")
    assert args.constraint_log == Path("constraints.jsonl")
    assert args.block_threshold == 1
    assert args.warn_threshold == 3
    assert args.fallback_threshold == 2
    assert args.warn_exposure_multiplier == 0.4
    assert args.record is True


def test_data_db_import_review_accepts_log_args():
    args = build_parser().parse_args(
        [
            "data",
            "db",
            "import-review",
            "--db-path",
            "quant.sqlite",
            "--tracker",
            "selections.jsonl",
            "--trade-plan-log",
            "trade_plans.jsonl",
            "--lifecycle-log",
            "lifecycle_snapshots.jsonl",
            "--state-log",
            "timeline_states.jsonl",
            "--approval-log",
            "order_approvals.jsonl",
        ]
    )

    assert args.db_command == "import-review"
    assert args.db_path == Path("quant.sqlite")
    assert args.trade_plan_log == Path("trade_plans.jsonl")
    assert args.lifecycle_log == Path("lifecycle_snapshots.jsonl")
    assert args.state_log == Path("timeline_states.jsonl")
    assert args.approval_log == Path("order_approvals.jsonl")


def test_data_db_doctor_accepts_format_and_output_args():
    args = build_parser().parse_args(
        [
            "data",
            "db",
            "doctor",
            "--db-path",
            "quant.sqlite",
            "--format",
            "markdown",
            "--output",
            "doctor.md",
        ]
    )

    assert args.db_command == "doctor"
    assert args.db_path == Path("quant.sqlite")
    assert args.format == "markdown"
    assert args.output == Path("doctor.md")


def test_review_doctor_accepts_jsonl_or_sqlite_args():
    args = build_parser().parse_args(
        [
            "review",
            "doctor",
            "--tracker",
            "selections.jsonl",
            "--trade-plan-log",
            "trade_plans.jsonl",
            "--confirm-log",
            "execution_confirms.jsonl",
            "--state-log",
            "timeline_states.jsonl",
            "--sqlite",
            "quant.sqlite",
            "--format",
            "markdown",
            "--output",
            "review_doctor.md",
        ]
    )

    assert args.review_command == "doctor"
    assert args.tracker == Path("selections.jsonl")
    assert args.trade_plan_log == Path("trade_plans.jsonl")
    assert args.confirm_log == Path("execution_confirms.jsonl")
    assert args.state_log == Path("timeline_states.jsonl")
    assert args.sqlite == Path("quant.sqlite")
    assert args.output == Path("review_doctor.md")


def test_review_lifecycle_history_accepts_args():
    args = build_parser().parse_args(
        [
            "review",
            "lifecycle-history",
            "--sqlite",
            "quant.sqlite",
            "--trade-plan-log",
            "trade_plans.jsonl",
            "--format",
            "markdown",
        ]
    )

    assert args.review_command == "lifecycle-history"
    assert args.sqlite == Path("quant.sqlite")
    assert args.trade_plan_log == Path("trade_plans.jsonl")
    assert args.format == "markdown"


def test_review_timeline_history_accepts_args():
    args = build_parser().parse_args(
        [
            "review",
            "timeline-history",
            "--state-log",
            "timeline_states.jsonl",
            "--sqlite",
            "quant.sqlite",
            "--format",
            "markdown",
        ]
    )

    assert args.review_command == "timeline-history"
    assert args.state_log == Path("timeline_states.jsonl")
    assert args.sqlite == Path("quant.sqlite")
    assert args.format == "markdown"


def test_review_timeline_watch_accepts_args():
    args = build_parser().parse_args(
        [
            "review",
            "timeline-watch",
            "--state-log",
            "timeline_states.jsonl",
            "--sqlite",
            "quant.sqlite",
            "--as-of",
            "2026-05-30",
            "--repeat-threshold",
            "3",
            "--stale-days",
            "2",
            "--format",
            "markdown",
        ]
    )

    assert args.review_command == "timeline-watch"
    assert args.state_log == Path("timeline_states.jsonl")
    assert args.sqlite == Path("quant.sqlite")
    assert args.as_of == "2026-05-30"
    assert args.repeat_threshold == 3
    assert args.stale_days == 2
    assert args.format == "markdown"
