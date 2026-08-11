# telegram-echo-bot

Bot de Telegram em FastAPI, rodando via webhook, que responde ao usuário
ecoando a mesma mensagem enviada. Pensado para hospedagem gratuita no Render
(free web service, que hiberna quando ocioso e acorda ao receber requisição).

## Rodando localmente

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # depois edite o .env com seu token real
uvicorn main:app --reload
```

## Criando o repositório no GitHub

1. Crie um repositório novo e vazio no GitHub (sem README, sem .gitignore —
   já temos os nossos).
2. No terminal, dentro desta pasta:

```bash
git add .
git commit -m "bot telegram inicial (eco) com FastAPI"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/telegram-echo-bot.git
git push -u origin main
```

## Deploy no Render

1. Crie um "Web Service" novo no Render, conectado a este repositório.
2. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Em "Environment", adicione as variáveis:
   - `TELEGRAM_BOT_TOKEN`
   - `DATABASE_URL` (connection string do Neon, quando for usar o banco)
4. Faça o deploy. Anote a URL pública que o Render gerar
   (ex: `https://telegram-echo-bot.onrender.com`).

## Registrando o webhook no Telegram

Depois do deploy, registre a URL do webhook (rode isso localmente, com o
`TELEGRAM_BOT_TOKEN` no ambiente):

```bash
python set_webhook.py set https://telegram-echo-bot.onrender.com/webhook
```

Para conferir se ficou configurado certo:

```bash
python set_webhook.py info
```

## Testando

Mande qualquer mensagem de texto para o bot no Telegram — ele deve responder
com a mesma mensagem (regra de eco).
