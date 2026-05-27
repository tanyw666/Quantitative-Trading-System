from __future__ import annotations

from dataclasses import asdict, dataclass

from quant_system.portfolio.positions import PositionBook


@dataclass(frozen=True)
class HoldingRiskCheck:
    name: str
    status: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HoldingRiskReport:
    status: str
    checks: list[HoldingRiskCheck]

    def to_dict(self) -> dict:
        return {"status": self.status, "checks": [check.to_dict() for check in self.checks]}


def check_holding_risk(
    book: PositionBook,
    stops: dict[str, float] | None = None,
    max_exposure_pct: float = 0.8,
    max_position_pct: float = 0.2,
) -> HoldingRiskReport:
    stops = {str(key).zfill(6): value for key, value in (stops or {}).items()}
    checks: list[HoldingRiskCheck] = [
        _check_total_exposure(book.total_exposure_pct, max_exposure_pct),
    ]

    for position in book.positions:
        checks.append(_check_position_exposure(position.symbol, position.exposure_pct, max_position_pct))
        if position.symbol in stops:
            checks.append(_check_stop(position.symbol, position.market_price, stops[position.symbol]))

    status = _rollup(checks)
    return HoldingRiskReport(status=status, checks=checks)


def _check_total_exposure(total_exposure_pct: float, max_exposure_pct: float) -> HoldingRiskCheck:
    if total_exposure_pct > max_exposure_pct:
        return HoldingRiskCheck(
            "total_exposure",
            "block",
            f"总暴露 {total_exposure_pct:.1%} 超过上限 {max_exposure_pct:.1%}。",
        )
    return HoldingRiskCheck("total_exposure", "pass", f"总暴露 {total_exposure_pct:.1%} 未超过上限 {max_exposure_pct:.1%}。")


def _check_position_exposure(symbol: str, exposure_pct: float | None, max_position_pct: float) -> HoldingRiskCheck:
    if exposure_pct is None:
        return HoldingRiskCheck("position_exposure", "warn", f"{symbol} 缺少当前价，无法评估单票暴露。")
    if exposure_pct > max_position_pct:
        return HoldingRiskCheck(
            "position_exposure",
            "block",
            f"{symbol} 单票暴露 {exposure_pct:.1%} 超过上限 {max_position_pct:.1%}。",
        )
    return HoldingRiskCheck("position_exposure", "pass", f"{symbol} 单票暴露 {exposure_pct:.1%} 未超过上限。")


def _check_stop(symbol: str, market_price: float | None, stop_price: float) -> HoldingRiskCheck:
    if market_price is None:
        return HoldingRiskCheck("stop_loss", "warn", f"{symbol} 缺少当前价，无法判断是否触发止损。")
    if market_price <= stop_price:
        return HoldingRiskCheck("stop_loss", "block", f"{symbol} 当前价 {market_price:.2f} 已触发止损 {stop_price:.2f}。")
    distance = market_price / stop_price - 1
    if distance <= 0.03:
        return HoldingRiskCheck("stop_loss", "warn", f"{symbol} 距离止损仅 {distance:.1%}。")
    return HoldingRiskCheck("stop_loss", "pass", f"{symbol} 当前价高于止损 {distance:.1%}。")


def _rollup(checks: list[HoldingRiskCheck]) -> str:
    statuses = {check.status for check in checks}
    if "block" in statuses:
        return "block"
    if "warn" in statuses:
        return "warn"
    return "pass"
