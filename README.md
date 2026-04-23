# MetaSimples

Sistema web de metas e performance comercial com foco em vendedores, autônomos e equipes pequenas.

## Rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
cp .env.example .env
python app.py
```

## Deploy no Railway

1. Suba este projeto para um repositório Git.
2. Crie um projeto no Railway.
3. Adicione um serviço PostgreSQL.
4. Configure as variáveis `SECRET_KEY` e `DATABASE_URL`.
5. O Railway usará o `Procfile` para iniciar via Gunicorn.

## Recursos incluídos

- Cadastro e login
- CSRF nos formulários
- PostgreSQL pronto para produção
- Dashboard com métricas e previsão
- Checklist diário
- Histórico com gráfico
- Configurações de meta
- Layout responsivo com identidade visual da G Tech
