from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean
from typing import Iterable

from models.finance_transaction import FinanceTransaction


CATEGORY_KEYWORDS = {
    'Alimentação fora': ['ifood', 'restaurante', 'burger', 'pizza', 'lanchonete', 'açaí', 'acai', 'sushi', 'delivery'],
    'Mercado': ['mercado', 'supermercado', 'atacadão', 'atacadao', 'assai', 'mix', 'hiper', 'carrefour'],
    'Transporte': ['uber', '99', 'posto', 'combustivel', 'combustível', 'gasolina', 'estacionamento', 'ônibus', 'onibus'],
    'Moradia': ['aluguel', 'condominio', 'condomínio', 'energia', 'equatorial', 'água', 'agua', 'internet', 'claro', 'vivo', 'tim'],
    'Assinaturas': ['netflix', 'spotify', 'amazon', 'prime', 'disney', 'max', 'icloud', 'google', 'academia', 'gym'],
    'Saúde': ['farmacia', 'farmácia', 'drogaria', 'consulta', 'exame', 'dentista', 'médico', 'medico'],
    'Educação': ['curso', 'faculdade', 'livro', 'udemy', 'alura', 'cisco'],
    'Lazer': ['cinema', 'bar', 'show', 'viagem', 'hotel', 'praia'],
    'Cartão': ['cartao', 'cartão', 'fatura'],
    'Renda': ['salario', 'salário', 'pix recebido', 'venda', 'cliente', 'freela', 'comissão', 'comissao'],
}


def _dec(value) -> Decimal:
    if value is None:
        return Decimal('0.00')
    return Decimal(str(value)).quantize(Decimal('0.01'))


def _money(value) -> str:
    value = _dec(value)
    return f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def suggest_category(text: str, tx_type: str = 'expense', user_id: int | None = None) -> str:
    """Categorização automática simples, local e explicável.

    Primeiro aprende pelo histórico do usuário/estabelecimento. Depois cai em palavras-chave.
    Isso entrega valor sem depender de API paga de IA.
    """
    raw = (text or '').strip()
    lowered = raw.lower()

    if user_id and raw:
        previous = (
            FinanceTransaction.query
            .filter(
                FinanceTransaction.user_id == user_id,
                FinanceTransaction.merchant.ilike(f'%{raw}%'),
                FinanceTransaction.category.isnot(None),
            )
            .order_by(FinanceTransaction.created_at.desc())
            .limit(8)
            .all()
        )
        if previous:
            categories = [item.category for item in previous if item.category]
            if categories:
                return Counter(categories).most_common(1)[0][0]

    if tx_type == 'income':
        return 'Renda'

    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category

    return 'Outros'


def month_range(year: int | None = None, month: int | None = None):
    today = date.today()
    year = year or today.year
    month = month or today.month
    start = date(year, month, 1)
    end = date(year + (month // 12), (month % 12) + 1, 1)
    return start, end


def get_transactions(user_id: int, start: date | None = None, end: date | None = None):
    query = FinanceTransaction.query.filter(FinanceTransaction.user_id == user_id)
    if start:
        query = query.filter(FinanceTransaction.date >= start)
    if end:
        query = query.filter(FinanceTransaction.date < end)
    return query.order_by(FinanceTransaction.date.desc(), FinanceTransaction.created_at.desc()).all()


def detect_subscriptions(transactions: Iterable[FinanceTransaction]):
    groups = defaultdict(list)
    for tx in transactions:
        if tx.type != 'expense':
            continue
        key = (tx.merchant or tx.description or tx.category or 'Sem descrição').strip().lower()
        if not key:
            continue
        groups[key].append(tx)

    subscriptions = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        amounts = [float(_dec(item.amount)) for item in items]
        avg = mean(amounts)
        tolerance = max(avg * 0.15, 5)
        similar = all(abs(value - avg) <= tolerance for value in amounts)
        months = {item.date.strftime('%Y-%m') for item in items}
        if similar and len(months) >= 2:
            total = sum((_dec(item.amount) for item in items), Decimal('0.00'))
            subscriptions.append({
                'name': items[0].merchant or items[0].description or items[0].category,
                'count': len(items),
                'average': _dec(avg),
                'total': total,
                'message': f"Possível assinatura: {items[0].merchant or items[0].description or items[0].category}. Média de {_money(avg)} e total de {_money(total)} no período.",
            })
    return subscriptions[:6]


def detect_anomalies(current_transactions: Iterable[FinanceTransaction], past_transactions: Iterable[FinanceTransaction]):
    current_by_cat = defaultdict(Decimal)
    past_by_cat = defaultdict(list)

    for tx in current_transactions:
        if tx.type == 'expense':
            current_by_cat[tx.category or 'Outros'] += _dec(tx.amount)

    for tx in past_transactions:
        if tx.type == 'expense':
            past_by_cat[tx.category or 'Outros'].append(_dec(tx.amount))

    alerts = []
    for category, current_total in current_by_cat.items():
        past_values = past_by_cat.get(category, [])
        if len(past_values) < 3:
            continue
        past_avg = sum(past_values, Decimal('0.00')) / Decimal(len(past_values))
        if past_avg > 0 and current_total > past_avg * Decimal('1.6'):
            percent = int(((current_total / past_avg) - 1) * 100)
            alerts.append({
                'category': category,
                'current': current_total,
                'average': past_avg,
                'percent': percent,
                'message': f"Alerta: seus gastos em {category} estão {percent}% acima do seu padrão recente.",
            })
    return alerts[:5]


def detect_micro_waste(transactions: Iterable[FinanceTransaction]):
    groups = defaultdict(list)
    for tx in transactions:
        if tx.type == 'expense' and _dec(tx.amount) <= Decimal('20.00'):
            groups[tx.category or 'Outros'].append(tx)

    wastes = []
    for category, items in groups.items():
        if len(items) >= 5:
            total = sum((_dec(item.amount) for item in items), Decimal('0.00'))
            wastes.append({
                'category': category,
                'count': len(items),
                'total': total,
                'message': f"Pequenos gastos em {category}: {len(items)} compras até R$ 20 somaram {_money(total)}.",
            })
    return sorted(wastes, key=lambda item: item['total'], reverse=True)[:5]


def compare_with_past(user_id: int, current_start: date):
    prev_end = current_start
    prev_month = current_start.month - 1 or 12
    prev_year = current_start.year if current_start.month > 1 else current_start.year - 1
    prev_start = date(prev_year, prev_month, 1)

    current = get_transactions(user_id, current_start, date(current_start.year + (current_start.month // 12), (current_start.month % 12) + 1, 1))
    previous = get_transactions(user_id, prev_start, prev_end)

    current_expense = sum((_dec(t.amount) for t in current if t.type == 'expense'), Decimal('0.00'))
    previous_expense = sum((_dec(t.amount) for t in previous if t.type == 'expense'), Decimal('0.00'))

    if not previous:
        return 'Ainda não tenho mês anterior suficiente para comparar seu progresso.'

    diff = previous_expense - current_expense
    if diff > 0:
        return f"Você está gastando {_money(diff)} a menos que no mês anterior. Bom sinal para repetir o padrão."
    if diff < 0:
        return f"Você está gastando {_money(abs(diff))} a mais que no mês anterior. Vale revisar as maiores categorias."
    return 'Seu gasto está praticamente igual ao mês anterior.'


def forecast_balance(transactions: Iterable[FinanceTransaction], days: int = 30):
    txs = list(transactions)
    today = date.today()
    income = sum((_dec(t.amount) for t in txs if t.type == 'income'), Decimal('0.00'))
    expense = sum((_dec(t.amount) for t in txs if t.type == 'expense'), Decimal('0.00'))
    balance = income - expense

    elapsed_days = max(today.day, 1)
    daily_expense_avg = expense / Decimal(elapsed_days) if elapsed_days else Decimal('0.00')
    projected_expense = daily_expense_avg * Decimal(days)
    projected_balance = balance - projected_expense

    risk = projected_balance < 0
    if risk:
        message = f"Risco de saldo negativo nos próximos {days} dias. Projeção aproximada: {_money(projected_balance)}."
    else:
        message = f"Se mantiver o ritmo atual, sua projeção para os próximos {days} dias é {_money(projected_balance)}."

    return {
        'daily_expense_avg': daily_expense_avg,
        'projected_balance': projected_balance,
        'risk': risk,
        'message': message,
    }


def saving_goal_suggestion(transactions: Iterable[FinanceTransaction]):
    expenses = [t for t in transactions if t.type == 'expense']
    if not expenses:
        return 'Lance seus gastos por alguns dias para eu sugerir uma meta de economia realista.'

    by_cat = defaultdict(Decimal)
    for tx in expenses:
        by_cat[tx.category or 'Outros'] += _dec(tx.amount)

    top = sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)[:2]
    if not top:
        return 'Ainda não há dados suficientes para sugerir uma meta.'

    target = sum((value for _, value in top), Decimal('0.00')) * Decimal('0.15')
    pieces = ' + '.join([f"reduzir {cat}" for cat, _ in top])
    return f"Meta realista: tentar economizar {_money(target)} este mês com {pieces}. Comece reduzindo 15% nas maiores categorias."


def best_bill_day_recommendation(transactions: Iterable[FinanceTransaction]):
    income_days = [tx.date.day for tx in transactions if tx.type == 'income']
    if not income_days:
        return 'Cadastre suas entradas principais para eu recomendar o melhor dia de vencimento das contas.'
    common_day = Counter(income_days).most_common(1)[0][0]
    suggested = min(common_day + 5, 28)
    return f"Melhor janela para pagar contas: por volta do dia {suggested}. Isso dá alguns dias após sua entrada mais comum e reduz risco de saldo apertado."


def natural_summary(total_income, total_expense, balance, top_category, top_category_value, selected_day=None):
    selected_day = selected_day or date.today().day
    return (
        f"Até o dia {selected_day}, entraram {_money(total_income)} e saíram {_money(total_expense)}. "
        f"Seu saldo do mês está em {_money(balance)}. A maior pressão até agora é {top_category}, com {_money(top_category_value)}."
    )


def build_finance_context(user_id: int, year: int | None = None, month: int | None = None):
    today = date.today()
    start, end = month_range(year, month)
    selected_year = start.year
    selected_month = start.month

    transactions = get_transactions(user_id, start, end)
    past_start = start - timedelta(days=95)
    past_transactions = get_transactions(user_id, past_start, start)

    total_income = sum((_dec(t.amount) for t in transactions if t.type == 'income'), Decimal('0.00'))
    total_expense = sum((_dec(t.amount) for t in transactions if t.type == 'expense'), Decimal('0.00'))
    balance = total_income - total_expense

    categories = defaultdict(Decimal)
    for item in transactions:
        if item.type == 'expense':
            categories[item.category or 'Outros'] += _dec(item.amount)

    category_items = sorted(categories.items(), key=lambda kv: kv[1], reverse=True)
    top_category = category_items[0][0] if category_items else 'Sem gastos'
    top_category_value = category_items[0][1] if category_items else Decimal('0.00')

    chart_labels = [item[0] for item in category_items[:8]]
    chart_values = [float(item[1]) for item in category_items[:8]]

    subscriptions = detect_subscriptions(get_transactions(user_id, past_start, end))
    anomalies = detect_anomalies(transactions, past_transactions)
    micro_wastes = detect_micro_waste(transactions)
    forecast = forecast_balance(transactions)
    past_comparison = compare_with_past(user_id, start)
    saving_goal = saving_goal_suggestion(transactions)
    bill_day_hint = best_bill_day_recommendation(get_transactions(user_id, past_start, end))
    summary = natural_summary(total_income, total_expense, balance, top_category, top_category_value, today.day)

    intelligence_cards = [
        {'title': 'Resumo amigável', 'body': summary},
        {'title': 'Previsão de saldo', 'body': forecast['message']},
        {'title': 'Meta de economia sugerida', 'body': saving_goal},
        {'title': 'Seu eu do passado', 'body': past_comparison},
        {'title': 'Melhor dia para pagar contas', 'body': bill_day_hint},
    ]

    for item in subscriptions:
        intelligence_cards.append({'title': 'Assinatura possível', 'body': item['message']})
    for item in anomalies:
        intelligence_cards.append({'title': 'Gasto fora do padrão', 'body': item['message']})
    for item in micro_wastes:
        intelligence_cards.append({'title': 'Pequeno desperdício recorrente', 'body': item['message']})

    return {
        'selected_year': selected_year,
        'selected_month': selected_month,
        'month_start': start,
        'transactions': transactions,
        'total_income': total_income,
        'total_expense': total_expense,
        'balance': balance,
        'top_category': top_category,
        'top_category_value': top_category_value,
        'category_items': category_items,
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'subscriptions': subscriptions,
        'anomalies': anomalies,
        'micro_wastes': micro_wastes,
        'forecast': forecast,
        'past_comparison': past_comparison,
        'saving_goal': saving_goal,
        'bill_day_hint': bill_day_hint,
        'natural_summary': summary,
        'intelligence_cards': intelligence_cards[:10],
    }
