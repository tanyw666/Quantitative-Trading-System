from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimits:
    max_position_pct: float = 0.2
    max_total_exposure: float = 0.8
    stop_loss_pct: float = 0.08
    max_single_day_loss_pct: float = 0.03

    def validate(self) -> None:
        for field_name, value in self.__dict__.items():
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
        if self.max_position_pct > self.max_total_exposure:
            raise ValueError("max_position_pct cannot exceed max_total_exposure")
