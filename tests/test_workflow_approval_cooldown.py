from argparse import Namespace
import json

import quant_system.cli as cli


def test_constraint_records_include_auto_approval_cooldown(tmp_path):
    approval_log = tmp_path / "order_approvals.jsonl"
    trade_log = tmp_path / "trades.jsonl"
    constraint_log = tmp_path / "strategy_constraints.jsonl"
    approval_log.write_text(
        '{"created_at":"2026-05-30T09:30:00+00:00","symbol":"000001","status":"block","confirmed_value":0,"suggested_quantity":0,"strategy":"dragon"}\n',
        encoding="utf-8",
    )
    trade_log.write_text(
        '{"date":"2026-05-30","symbol":"000001","strategy":"dragon","side":"BUY","price":10,"quantity":100,"amount":1000,"order_approval_created_at":"2026-05-30T09:30:00+00:00","review":"violation"}\n',
        encoding="utf-8",
    )
    args = Namespace(
        sqlite=None,
        approval_log=approval_log,
        trade_log=trade_log,
        journal=trade_log,
        constraint_log=constraint_log,
        disable_approval_cooldown=False,
        approval_lookahead_days=1,
        approval_value_tolerance_pct=0.02,
        approval_block_threshold=1,
        approval_warn_threshold=2,
        approval_fallback_threshold=2,
        approval_warn_exposure_multiplier=0.5,
        limit=20,
    )

    records = cli._constraint_records_from_args(args)

    assert len(records) == 1
    assert records[0]["source"] == "review.approval-audit"
    assert records[0]["strategy"] == "dragon"
    assert records[0]["alert_level"] == "block"


def test_record_auto_approval_cooldown_dedupes_same_day(tmp_path):
    approval_log = tmp_path / "order_approvals.jsonl"
    trade_log = tmp_path / "trades.jsonl"
    constraint_log = tmp_path / "strategy_constraints.jsonl"
    approval_log.write_text(
        '{"created_at":"2026-05-30T09:30:00+00:00","symbol":"000001","status":"block","confirmed_value":0,"suggested_quantity":0,"strategy":"dragon"}\n',
        encoding="utf-8",
    )
    trade_log.write_text(
        '{"date":"2026-05-30","symbol":"000001","strategy":"dragon","side":"BUY","price":10,"quantity":100,"amount":1000,"order_approval_created_at":"2026-05-30T09:30:00+00:00","review":"violation"}\n',
        encoding="utf-8",
    )
    args = Namespace(
        sqlite=None,
        approval_log=approval_log,
        trade_log=trade_log,
        journal=trade_log,
        constraint_log=constraint_log,
        disable_approval_cooldown=False,
        record_approval_cooldown=True,
        approval_lookahead_days=1,
        approval_value_tolerance_pct=0.02,
        approval_block_threshold=1,
        approval_warn_threshold=2,
        approval_fallback_threshold=2,
        approval_warn_exposure_multiplier=0.5,
        limit=20,
    )

    first = cli._record_auto_approval_cooldown_from_args(args)
    args._auto_approval_cooldown_payload = None
    second = cli._record_auto_approval_cooldown_from_args(args)

    rows = [json.loads(line) for line in constraint_log.read_text(encoding="utf-8").splitlines()]
    assert first["persisted_count"] == 1
    assert second["persisted_count"] == 0
    assert second["skipped_existing_count"] == 1
    assert len(rows) == 1


def test_record_auto_approval_cooldown_keeps_cross_day_history(tmp_path, monkeypatch):
    approval_log = tmp_path / "order_approvals.jsonl"
    trade_log = tmp_path / "trades.jsonl"
    constraint_log = tmp_path / "strategy_constraints.jsonl"
    approval_log.write_text(
        "\n".join(
            [
                '{"created_at":"2026-05-30T09:30:00+00:00","symbol":"000001","status":"block","confirmed_value":0,"suggested_quantity":0,"strategy":"dragon"}',
                '{"created_at":"2026-05-31T09:30:00+00:00","symbol":"000001","status":"block","confirmed_value":0,"suggested_quantity":0,"strategy":"dragon"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    trade_log.write_text(
        "\n".join(
            [
                '{"date":"2026-05-30","symbol":"000001","strategy":"dragon","side":"BUY","price":10,"quantity":100,"amount":1000,"order_approval_created_at":"2026-05-30T09:30:00+00:00","review":"violation"}',
                '{"date":"2026-05-31","symbol":"000001","strategy":"dragon","side":"BUY","price":10,"quantity":100,"amount":1000,"order_approval_created_at":"2026-05-31T09:30:00+00:00","review":"violation"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        sqlite=None,
        approval_log=approval_log,
        trade_log=trade_log,
        journal=trade_log,
        constraint_log=constraint_log,
        disable_approval_cooldown=False,
        record_approval_cooldown=True,
        approval_lookahead_days=1,
        approval_value_tolerance_pct=0.02,
        approval_block_threshold=1,
        approval_warn_threshold=2,
        approval_fallback_threshold=2,
        approval_warn_exposure_multiplier=0.5,
        limit=20,
    )

    monkeypatch.setattr(
        cli,
        "build_approval_cooldown_constraints",
        lambda *args, **kwargs: [
            {
                "created_at": "2026-05-30T10:00:00+00:00",
                "source": "review.approval-audit",
                "strategy": "dragon",
                "symbol": "000001",
                "alert_level": "block",
                "action": "pause",
                "alerts": ["approval_cooldown", "approval_block"],
                "note": "same violation",
            },
            {
                "created_at": "2026-05-31T10:00:00+00:00",
                "source": "review.approval-audit",
                "strategy": "dragon",
                "symbol": "000001",
                "alert_level": "block",
                "action": "pause",
                "alerts": ["approval_cooldown", "approval_block"],
                "note": "same violation",
            },
        ],
    )

    result = cli._record_auto_approval_cooldown_from_args(args)

    rows = [json.loads(line) for line in constraint_log.read_text(encoding="utf-8").splitlines()]
    assert result["persisted_count"] == 2
    assert result["skipped_existing_count"] == 0
    assert [row["created_at"][:10] for row in rows] == ["2026-05-30", "2026-05-31"]
