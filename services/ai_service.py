from __future__ import annotations

import requests
from flask import current_app


def _local_finance_answer(question: str) -> str:
    q = (question or '').lower()
    if any(word in q for word in ['gasto', 'gastei', 'saída', 'saida', 'categoria']):
        return (
            'Pelo controle G Tech, comece separando seus gastos por categoria: alimentação, transporte, casa, cartão, lazer e investimento. '
            'Depois observe qual categoria mais pesa no mês e defina uma redução pequena, realista e semanal. O objetivo não é cortar tudo, é recuperar clareza e constância.'
        )
    if any(word in q for word in ['meta', 'venda', 'vender', 'comissão', 'comissao']):
        return (
            'Para bater sua meta, transforme o valor mensal em meta diária. Depois acompanhe todos os dias: valor vendido, atendimentos e fechamentos. '
            'Se você estiver abaixo do ritmo, aumente follow-up e propostas antes de tentar mudar o plano inteiro.'
        )
    if any(word in q for word in ['saldo', 'entrou', 'entrada']):
        return (
            'Saldo saudável é entrada menos saída com previsibilidade. Lance primeiro tudo que entrou, depois todos os compromissos fixos, e só então analise o saldo livre real. '
            'Isso evita achar que sobrou dinheiro quando ainda existem contas pendentes.'
        )
    return (
        'Sou o assistente G Tech. Para te ajudar melhor, me diga seu objetivo em uma frase: organizar gastos, aumentar vendas, bater meta ou entender seu saldo. '
        'Com isso eu consigo sugerir o próximo passo de forma simples e prática.'
    )


def ask_ai(question: str, context: str = '') -> tuple[bool, str]:
    provider = current_app.config.get('AI_PROVIDER', 'local').lower().strip()
    api_key = current_app.config.get('AI_API_KEY', '').strip()
    model = current_app.config.get('AI_MODEL', 'llama-3.1-8b-instant')

    if provider in ('local', '', 'none') or not api_key:
        return True, _local_finance_answer(question)

    if provider == 'groq':
        url = current_app.config.get('AI_API_BASE_URL') or 'https://api.groq.com/openai/v1/chat/completions'
    elif provider == 'xai':
        url = current_app.config.get('AI_API_BASE_URL') or 'https://api.x.ai/v1/chat/completions'
    elif provider == 'openrouter':
        url = current_app.config.get('AI_API_BASE_URL') or 'https://openrouter.ai/api/v1/chat/completions'
    else:
        return True, _local_finance_answer(question)

    messages = [
        {'role': 'system', 'content': 'Você é o assistente financeiro e de metas da G Tech. Responda em português do Brasil, com clareza, foco prático e sem prometer resultado garantido.'},
        {'role': 'user', 'content': f'Contexto do usuário: {context}\n\nPergunta: {question}'},
    ]

    try:
        response = requests.post(
            url,
            json={'model': model, 'messages': messages, 'temperature': 0.4, 'max_tokens': 450},
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            timeout=18,
        )
        if response.status_code >= 400:
            current_app.logger.error('Erro IA %s: %s', response.status_code, response.text)
            return True, _local_finance_answer(question)
        data = response.json()
        answer = data.get('choices', [{}])[0].get('message', {}).get('content')
        return True, answer or _local_finance_answer(question)
    except requests.RequestException:
        current_app.logger.exception('Falha ao chamar IA externa')
        return True, _local_finance_answer(question)
