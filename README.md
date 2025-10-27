# ConfirmaTudoBack (Python)

Repositório **confirmatudoback-python** — API em Python (Flask + Playwright) pronta para deploy no Render.

## Estrutura
```
confirmatudoback-python/
├── app.py
├── requirements.txt
├── .env
└── README.md
```

## Variáveis de ambiente
Arquivo `.env` já está preenchido com as URLs fornecidas:
- `PORT=10000`
- `BASE_URL=https://confirmatudoback.onrender.com`
- `FRONTEND_URL=https://confirmatudo.lovable.app`
- `IFOOD_URL=https://confirmacao-entrega-propria.ifood.com.br/numero-pedido`
- `NINENINE_URL=https://food-b-h5.99app.com/pt-BR/v2/confirmation-entrega/locator`

> **Importante:** Não compartilhe credenciais sensíveis neste repositório público.

## Como rodar localmente

1. Crie e ative um virtualenv (opcional mas recomendado):
```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate    # Windows
```

2. Instale dependências:
```bash
pip install -r requirements.txt
python -m playwright install chromium
```

3. Rode a API:
```bash
python app.py
```

Acesse `http://localhost:10000/health` para testar.

## Deploy no Render (Docker-less)

1. Crie um novo *Web Service* no Render e conecte ao seu repositório GitHub.
2. Escolha a branch e configure:
   - Environment: `Python 3`
   - Build Command:
     ```
     pip install -r requirements.txt
     python -m playwright install chromium
     ```
   - Start Command:
     ```
     gunicorn --bind 0.0.0.0:$PORT app:app --workers 1 --threads 4
     ```
3. Adicione as Environment Variables no painel do Render (caso queira sobrescrever):
   - `PORT`, `BASE_URL`, `FRONTEND_URL`, `IFOOD_URL`, `NINENINE_URL`
4. Deploy — Render irá construir e subir o serviço.

> Observação: Playwright precisa instalar o Chromium durante a build (`playwright install chromium`). Se você preferir usar Docker, é mais controlado; me avise que eu já monto um `Dockerfile` pronto.

## Como usar a API

**POST** `/confirmar-entrega`
```json
{
  "localizador": "12345678",
  "codigo": "1234"
}
```

Respostas:
- Success (200):
```json
{ "plataforma": "iFood", "success": true, "message": "Entrega confirmada no iFood!" }
```
- Error (404) exemplo:
```json
{ "success": false, "reason": "localizador_invalido", "message": "Localizador inválido (não avançou para tela de código)." }
```

## Observações importantes
- As páginas alvo podem mudar a qualquer momento; seletores podem precisar ser ajustados.
- Algumas proteções (CAPTCHAs, rate limits) podem impedir a automação.
- Use com responsabilidade e respeito aos Termos de Serviço das plataformas.
