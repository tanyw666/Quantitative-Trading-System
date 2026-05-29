from argparse import Namespace

import pandas as pd

from quant_system import cli


def test_source_or_default_prefers_explicit_value():
    args = Namespace(settings=None)
    assert cli.source_or_default(args, "mootdx", "daily_source", "auto") == "mootdx"


def test_source_or_default_uses_settings_when_auto(monkeypatch):
    class FakeSources:
        daily_source = "tencent"

    class FakeSettings:
        data_sources = FakeSources()

    monkeypatch.setattr(cli, "source_from_args", lambda args, attr, default="auto": getattr(FakeSources, attr))
    args = Namespace(settings=None)
    assert cli.source_or_default(args, "auto", "daily_source", "auto") == "tencent"


def test_cache_needs_refresh_only_when_stale():
    cached = pd.DataFrame({"date": ["2026-05-28"]})

    assert cli._cache_needs_refresh(cached, "20260529", refresh_stale_days=2) is False
    assert cli._cache_needs_refresh(cached, "20260601", refresh_stale_days=2) is True


def test_cache_needs_refresh_ignores_threshold_when_disabled():
    cached = pd.DataFrame({"date": ["2026-05-20"]})

    assert cli._cache_needs_refresh(cached, "20260529", refresh_stale_days=None) is False
