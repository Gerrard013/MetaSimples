# MetaSimples + Controle G Tech — versão corrigida para produção

## O que foi corrigido

- Separação dura de produto:
  - Conta `controle` entra em `/finance`.
  - Conta `metasimples` entra em `/onboarding` ou `/dashboard`.
  - Se tentar entrar no painel errado, o sistema redireciona para o produto correto.
- Landing page refeita para usuário final, sem linguagem de desenvolvedor.
- Cards de preço com contraste branco e legível.
- Preço mensal corrigido para não ficar igual ao trimestral.
- Mercado Pago por preferência/checkout:
  - Pix e cartão ficam disponíveis conforme sua conta Mercado Pago.
  - Taxa configurável e somada no valor cobrado do cliente.
  - Webhook sincroniza pagamento aprovado e libera acesso.
- RPA de resumo financeiro por e-mail via Resend.
- IA funcionando em modo local sem token; pode ligar Groq/xAI/OpenRouter por env.
- OCR ficou fora desta versão, como solicitado.

## Preços padrão configurados

Valores base líquidos, antes da taxa Mercado Pago:

- 1 mês: R$ 150,00
- 3 meses: R$ 299,70 à vista, equivalente a R$ 99,90/mês
- 1 ano: R$ 958,80 à vista, equivalente a R$ 79,90/mês

Esses valores são mais coerentes porque o trimestral e o anual têm desconto real, mas não ficam iguais ao mensal.

## Variáveis obrigatórias no Railway

Cole no serviço WEB/App, não no Postgres:

```env
SECRET_KEY=troque_por_uma_chave_forte
FLASK_ENV=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
APP_NAME=G Tech Platform
APP_BASE_URL=https://seu-app.up.railway.app
SUPPORT_WHATSAPP=5591999999999
DEFAULT_TRIAL_DAYS=7

ADMIN_EMAIL=seu_email_admin
ADMIN_PASSWORD=sua_senha_admin_forte

MAIL_ENABLED=true
EMAIL_PROVIDER=resend
RESEND_API_KEY=sua_chave_resend
MAIL_FROM_NAME=G Tech
MAIL_FROM_EMAIL=email_verificado_no_resend

MERCADOPAGO_ACCESS_TOKEN=seu_access_token_mercado_pago
MERCADOPAGO_PUBLIC_KEY=sua_public_key_mercado_pago
MERCADOPAGO_STATEMENT_DESCRIPTOR=GTECH
MERCADOPAGO_MAX_INSTALLMENTS=3
MERCADOPAGO_FEE_PERCENT=5.31
MERCADOPAGO_FEE_FIXED=0.00

PLAN_CONTROLE_MENSAL_PRICE=150.00
PLAN_CONTROLE_TRIMESTRAL_PRICE=299.70
PLAN_CONTROLE_ANUAL_PRICE=958.80
PLAN_METASIMPLES_MENSAL_PRICE=150.00
PLAN_METASIMPLES_TRIMESTRAL_PRICE=299.70
PLAN_METASIMPLES_ANUAL_PRICE=958.80

PAYMENT_REQUIRED_BEFORE_ACCESS=false

AI_PROVIDER=local
AI_API_KEY=
AI_MODEL=llama-3.1-8b-instant
AI_API_BASE_URL=
```

## Para ligar Groq

```env
AI_PROVIDER=groq
AI_API_KEY=sua_chave_groq
AI_MODEL=llama-3.1-8b-instant
AI_API_BASE_URL=https://api.groq.com/openai/v1/chat/completions
```

## Para ligar Grok/xAI

```env
AI_PROVIDER=xai
AI_API_KEY=sua_chave_xai
AI_MODEL=modelo_ativo_no_painel_xai
AI_API_BASE_URL=https://api.x.ai/v1/chat/completions
```

## Mercado Pago

Use o Access Token de produção quando for vender de verdade. O webhook do Mercado Pago deve apontar para:

```text
https://seu-app.up.railway.app/webhooks/mercadopago
```

O checkout cria a preferência pelo backend. O app salva o pagamento pendente, consulta o pagamento aprovado e libera o usuário pelo período do plano:

- mensal: 30 dias
- trimestral: 90 dias
- anual: 365 dias

## Rotas principais

- Landing: `/`
- Cadastro Controle: `/register?plan=controle`
- Cadastro MetaSimples: `/register?plan=metasimples`
- Login Controle: `/login?plan=controle`
- Login MetaSimples: `/login?plan=metasimples`
- Controle G Tech: `/finance`
- MetaSimples: `/onboarding` e `/dashboard`
- IA financeira: `/assistant`
- Admin: `/admin/login`

## Start command Railway

```bash
gunicorn --bind 0.0.0.0:$PORT app:app
```

## Checklist antes de divulgar

1. Subir ZIP/repo no GitHub.
2. Conectar no Railway.
3. Colocar Postgres.
4. Colar variáveis no serviço web.
5. Conferir `APP_BASE_URL` com domínio real.
6. Testar cadastro Controle.
7. Testar cadastro MetaSimples.
8. Testar login de cada produto.
9. Testar pagamento sandbox/produção no Mercado Pago.
10. Testar envio de resumo por e-mail no painel Controle.

