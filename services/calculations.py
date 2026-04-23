from __future__ import annotations

from typing import Iterable


def calculate_month_sales_target(target_income_month: float, commission_percent: float) -> float:
    """If commission is informed, convert desired income into required sales.
    If commission is zero, treat the monthly target as the sales target itself.
    """
    if commission_percent > 0:
        return round(target_income_month / (commission_percent / 100), 2)
    return round(target_income_month, 2)


def calculate_day_sales_target(target_sales_month: float, working_days_month: int) -> float:
    return round(target_sales_month / working_days_month, 2) if working_days_month > 0 else 0.0


def calculate_earnings_from_sales(sales_value: float, commission_percent: float) -> float:
    if commission_percent > 0:
        return round(sales_value * (commission_percent / 100), 2)
    return round(sales_value, 2)


def calculate_progress(current: float, target: float) -> float:
    if target <= 0:
        return 0.0
    return round(min((current / target) * 100, 100), 2)


def calculate_remaining(target: float, current: float) -> float:
    return round(max(target - current, 0), 2)


def calculate_conversion_rate(closed_deals: int, attendance_count: int) -> float:
    if attendance_count <= 0:
        return 0.0
    return round((closed_deals / attendance_count) * 100, 2)


def calculate_average(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)
