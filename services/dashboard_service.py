from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from models.checklist import ChecklistEntry
from models.daily_result import DailyResult
from models.goal import Goal
from services.calculations import (
    calculate_average,
    calculate_conversion_rate,
    calculate_progress,
    calculate_remaining,
)


def _safe_float(value, default=0.0) -> float:
    try:
        if value is None or value == '':
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value, default=0) -> int:
    try:
        if value is None or value == '':
            return int(default)
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def build_dashboard_context(user_id: int, goal: Goal) -> dict[str, Any]:
    today = date.today()
    month_start = today.replace(day=1)

    results = (
        DailyResult.query
        .filter(DailyResult.user_id == user_id, DailyResult.date >= month_start, DailyResult.date <= today)
        .order_by(DailyResult.date.asc())
        .all()
    )

    checklist = ChecklistEntry.query.filter_by(user_id=user_id, date=today).first()
    results_by_date = {item.date: item for item in results}
    today_result = results_by_date.get(today)

    total_sales_month = round(sum(_safe_float(item.sales_value, 0) for item in results), 2)
    total_earnings_month = round(sum(_safe_float(item.earnings_value, 0) for item in results), 2)
    total_attendances = sum(_safe_int(item.attendance_count, 0) for item in results)
    total_closures = sum(_safe_int(item.closed_deals, 0) for item in results)

    sales_today = _safe_float(today_result.sales_value, 0) if today_result else 0.0
    earnings_today = _safe_float(today_result.earnings_value, 0) if today_result else 0.0

    goal_target_sales_day = _safe_float(goal.target_sales_day, 0)
    goal_working_days_month = _safe_int(goal.working_days_month, 0)
    goal_target_sales_month = _safe_float(goal.target_sales_month, 0)

    days_elapsed = today.day
    expected_until_today = round(goal_target_sales_day * days_elapsed, 2)
    rhythm_difference = round(total_sales_month - expected_until_today, 2)
    projection_month = (
        round((total_sales_month / days_elapsed) * goal_working_days_month, 2)
        if days_elapsed > 0 else 0.0
    )

    missing_to_projection = round(goal_target_sales_month - projection_month, 2)
    rhythm_status = (
        'Você está acima do ritmo esperado do mês.'
        if rhythm_difference >= 0
        else 'Você está abaixo do ritmo esperado do mês.'
    )
    rhythm_hint = (
        f'Excelente. Você está R$ {abs(rhythm_difference):,.2f} acima do ritmo.'
        if rhythm_difference >= 0
        else f'Hoje você precisa recuperar R$ {abs(rhythm_difference):,.2f} para voltar ao plano.'
    )

    progress_month = calculate_progress(total_sales_month, goal_target_sales_month)
    progress_day = calculate_progress(sales_today, goal_target_sales_day)
    remaining_month = calculate_remaining(goal_target_sales_month, total_sales_month)
    remaining_day = calculate_remaining(goal_target_sales_day, sales_today)
    average_daily_sales = calculate_average(_safe_float(item.sales_value, 0) for item in results)
    conversion_rate = calculate_conversion_rate(total_closures, total_attendances)

    best_day = max(results, key=lambda item: _safe_float(item.sales_value, 0), default=None)
    worst_day = min(results, key=lambda item: _safe_float(item.sales_value, 0), default=None)

    last_7_days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    chart_labels = [d.strftime('%d/%m') for d in last_7_days]
    chart_values = [
        round(_safe_float(results_by_date.get(d).sales_value, 0), 2) if results_by_date.get(d) else 0
        for d in last_7_days
    ]

    checklist_score = 0
    if checklist:
        checklist_score = sum([
            bool(checklist.leads_answered),
            bool(checklist.follow_up_done),
            bool(checklist.proposals_sent),
            bool(checklist.post_sale_done),
            bool(checklist.goal_reviewed),
        ])

    return {
        'today': today,
        'results': list(reversed(results[-7:])),
        'total_sales_month': total_sales_month,
        'total_earnings_month': total_earnings_month,
        'sales_today': sales_today,
        'earnings_today': earnings_today,
        'progress_month': progress_month,
        'progress_day': progress_day,
        'remaining_month': remaining_month,
        'remaining_day': remaining_day,
        'expected_until_today': expected_until_today,
        'rhythm_difference': rhythm_difference,
        'rhythm_status': rhythm_status,
        'rhythm_hint': rhythm_hint,
        'projection_month': projection_month,
        'missing_to_projection': missing_to_projection,
        'average_daily_sales': average_daily_sales,
        'conversion_rate': conversion_rate,
        'best_day': best_day,
        'worst_day': worst_day,
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'checklist_score': checklist_score,
        'checklist': checklist,
        'days_elapsed': days_elapsed,
    }
