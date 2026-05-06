# MetaSimples + Controle de Gastos G Tech

Versão pronta para testar com:

- Resend API para confirmação de e-mail.
- Mercado Pago Checkout Preferences para pagamento por plano.
- Landing page moderna com Controle de Gastos R$ 49,90 e MetaSimples R$ 79,90.
- Controle de Gastos com entradas, saídas, categorias, dashboard e histórico.
- IA G Tech local grátis, com opção de ligar API externa depois.

## Railway Variables

Copie `.env.production.example` para as variáveis do serviço Flask no Railway. Não coloque no serviço Postgres.

Obrigatórias para e-mail:

```env
MAIL_ENABLED=true
EMAIL_PROVIDER=resend
RESEND_API_KEY=...
MAIL_FROM_NAME=MetaSimples
MAIL_FROM_EMAIL=onboarding@resend.dev
```

Obrigatórias para Mercado Pago:

```env
MERCADOPAGO_ACCESS_TOKEN=APP_USR-...
MERCADOPAGO_PUBLIC_KEY=APP_USR-...
PLAN_CONTROLE_PRICE=49.90
PLAN_METASIMPLES_PRICE=79.90
```

## Deploy

```bash
git add .
git commit -m "Release G Tech plans with Resend, Mercado Pago and finance dashboard"
git push
```

No Railway, faça redeploy do serviço Flask.

## Teste

1. Acesse `/` e escolha um plano.
2. Crie cadastro novo.
3. Confirme o e-mail recebido pelo Resend.
4. Faça login.
5. Teste `/finance`.
6. Teste `/assistant`.
7. Teste `/payment?plan=controle` e `/payment?plan=metasimples` depois de configurar o token do Mercado Pago.
