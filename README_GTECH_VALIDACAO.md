# G Tech Platform — Validação local antes de produção

## Objetivo desta versão

Esta versão separa profissionalmente os dois produtos:

- **MetaSimples — R$ 79,90/mês**: metas, vendas, atendimentos, checklist e performance comercial.
- **Controle de Gastos G Tech — R$ 49,90/mês**: entradas, saídas, categorias, saldo e inteligência financeira.

Quem se cadastra no Controle entra em `/finance`. Quem se cadastra no MetaSimples entra no fluxo de metas `/onboarding` e `/dashboard`.

## Variáveis principais

Use `.env.production.example` como base. Para testar local, pode usar SQLite:

```env
FLASK_ENV=development
DATABASE_URL=sqlite:///metasimples_local.db
MAIL_ENABLED=false
PAYMENT_REQUIRED_BEFORE_ACCESS=false
```

Para produção:

```env
FLASK_ENV=production
DATABASE_URL=postgresql://...
MAIL_ENABLED=true
EMAIL_PROVIDER=resend
RESEND_API_KEY=...
MERCADOPAGO_ACCESS_TOKEN=...
APP_BASE_URL=https://metasimples-production.up.railway.app
```

## Modo de pagamento

- `PAYMENT_REQUIRED_BEFORE_ACCESS=false`: cadastro libera trial de 7 dias.
- `PAYMENT_REQUIRED_BEFORE_ACCESS=true`: cadastro leva o usuário para pagamento antes de usar.

## Checklist local

1. `python app.py` inicia sem erro.
2. `/` abre.
3. `/register?plan=controle` cria usuário e leva para `/finance`.
4. Usuário Controle não consegue entrar em `/dashboard` do MetaSimples.
5. `/finance/new?type=expense` salva saída.
6. `/finance` mostra saldo, categorias e inteligência.
7. `/assistant` abre para usuário Controle.
8. `/register?plan=metasimples` cria usuário e leva para `/onboarding`.
9. Usuário MetaSimples não consegue entrar em `/finance`.
10. `/payment?plan=controle` cria preferência Mercado Pago quando `MERCADOPAGO_ACCESS_TOKEN` estiver configurado.

## Inteligência financeira implementada nesta versão

- Categorização automática local por estabelecimento/palavra-chave.
- Aprendizado simples pelo histórico do usuário.
- Detecção de possíveis assinaturas recorrentes.
- Previsão de saldo para os próximos 30 dias.
- Alerta de gasto fora do padrão.
- Sugestão de meta de economia realista.
- Resumo amigável em linguagem natural.
- Descoberta de pequenos desperdícios recorrentes.
- Comparação com o mês anterior.
- Sugestão de melhor janela para pagar contas.

## OCR de recibos

A estrutura do produto já prevê OCR, mas esta versão não liga OCR real ainda. Para produção, integre depois com uma API específica de OCR/vision. O app atual já fica vendável sem OCR, pois entrega o core financeiro e insights.
