# Imagem da API do Clave.
#   docker build -t clave .
#   docker run -p 8010:7860 --env-file .env clave      → http://localhost:8010/docs
# As chaves entram na hora de rodar (--env-file); nunca ficam dentro da imagem.

FROM python:3.12-slim

# uv em versão fixa, copiado da imagem oficial: todo build sai igual.
COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1º só a lista de bibliotecas: enquanto ela não mudar, o Docker reaproveita esta camada
#    e pula a instalação quando só o código muda.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# 2º o código e os dados (o código acha data/raw e .sessions pela estrutura do projeto).
COPY src ./src
COPY data ./data
RUN uv sync --frozen --no-dev

# Usuário sem privilégios (id 1000, o que o Hugging Face Spaces usa), que só escreve nas conversas.
RUN useradd --uid 1000 --create-home clave && mkdir -p /app/.sessions && chown -R clave /app/.sessions
USER clave

# 0.0.0.0 = aceitar conexões de fora do container; 7860 = porta padrão do Hugging Face Spaces.
ENV HOST=0.0.0.0 \
    PORT=7860 \
    PATH="/app/.venv/bin:$PATH"
EXPOSE 7860

# O próprio Docker chama /saude periodicamente e marca o container como "unhealthy" se parar.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/saude', timeout=4)"

CMD ["emporio-api"]
