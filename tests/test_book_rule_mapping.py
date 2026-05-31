from pathlib import Path

import yaml


RULEBOOK = Path("configs/rules/book_rule_mapping.yaml")


def test_book_rule_mapping_has_all_route_layers():
    payload = yaml.safe_load(RULEBOOK.read_text(encoding="utf-8"))

    assert set(payload["layers"]) == {"selection", "entry", "sizing", "exit", "discipline"}


def test_book_rule_mapping_rules_have_required_fields_and_targets():
    payload = yaml.safe_load(RULEBOOK.read_text(encoding="utf-8"))
    required = set(payload["required_rule_fields"])
    rules = [
        rule
        for layer in payload["layers"].values()
        for rule in layer["rules"]
    ]

    assert rules
    for rule in rules:
        assert required.issubset(rule)
        assert rule["layer"] in payload["layers"]
        assert rule["id"].startswith(f"{rule['layer']}.")
        assert rule["source_books"]
        assert rule["quant_rules"]
        assert rule["manual_checks"]
        assert rule["system_targets"]
        assert rule["rollout_priority"] in {"P0", "P1", "P2"}


def test_book_rule_mapping_p0_rules_cover_the_trading_loop():
    payload = yaml.safe_load(RULEBOOK.read_text(encoding="utf-8"))
    p0_layers = {
        rule["layer"]
        for layer in payload["layers"].values()
        for rule in layer["rules"]
        if rule["rollout_priority"] == "P0"
    }

    assert p0_layers == {"selection", "entry", "sizing", "exit", "discipline"}


def test_book_rule_mapping_covers_every_user_book():
    payload = yaml.safe_load(RULEBOOK.read_text(encoding="utf-8"))
    expected_books = {
        "Japanese Candlestick Charting Techniques",
        "Reminiscences of a Stock Operator",
        "Security Analysis",
        "The Intelligent Investor",
        "Berkshire Hathaway Letters to Shareholders",
        "Volume Price Analysis",
        "Tape Reading and Market Tactics",
        "Methods of a Wall Street Master",
        "Trading in the Zone",
        "Tao Te Ching",
        "The Art of War",
        "The Four Books and Five Classics",
        "The Thirty-Six Stratagems",
        "The Greatest Salesman in the World",
        "How to Win Friends and Influence People",
        "Hundred Schools of Thought",
        "Romance of the Three Kingdoms",
    }
    covered_books = {
        book
        for layer in payload["layers"].values()
        for rule in layer["rules"]
        for book in rule["source_books"]
    }

    assert expected_books.issubset(covered_books)


def test_book_rule_mapping_has_explicit_user_book_coverage():
    payload = yaml.safe_load(RULEBOOK.read_text(encoding="utf-8"))
    expected_user_titles = {
        "日本蜡烛图技术",
        "股票大作手回忆录",
        "证券分析",
        "聪明的投资者",
        "巴菲特致股东信",
        "量价分析",
        "解读盘口",
        "专业投机原理",
        "交易心理分析",
        "道德经",
        "孙子兵法",
        "四书五经",
        "三十六计",
        "羊皮卷",
        "人性的弱点",
        "诸子百家",
        "三国",
    }
    coverage = payload["user_book_coverage"]
    rule_ids = {
        rule["id"]
        for layer in payload["layers"].values()
        for rule in layer["rules"]
    }

    assert expected_user_titles == set(coverage)
    for item in coverage.values():
        assert item["canonical"]
        assert item["rule_ids"]
        assert set(item["rule_ids"]).issubset(rule_ids)
