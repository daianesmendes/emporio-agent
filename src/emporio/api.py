"""API HTTP do agente (FastAPI).

É só outra porta de entrada para o mesmo Agent.reply() que o terminal usa:
ferramentas, verificações finais e a regra de LGPD continuam no agente.

  uv run emporio-api                      # sobe em http://localhost:8000 (docs em /docs)
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import date

from pathlib import Path as FilePath

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import config
from .agent import Agent
from .data import Store
from .llm import LLMClient

# O id da conversa vira nome de arquivo (.sessions/{id}.json): só letras, números, "-" e "_".
# Sem isso, um id como "../../.env" tentaria ler ou sobrescrever arquivos do servidor (path traversal).
CHAT_PAGE = FilePath(__file__).parent / "web" / "index.html"

ConversaId = Path(pattern=r"^[A-Za-z0-9_-]{1,64}$", description="Identificador da conversa, escolhido pelo cliente.")


# ----------------------------------------------------------------------
# Formatos de entrada e saída (validam e documentam ao mesmo tempo)
# ----------------------------------------------------------------------
class MensagemEntrada(BaseModel):
    texto: str = Field(min_length=1, max_length=1000, examples=["Quanto custa o Takamine GD20?"])


class FerramentaUsada(BaseModel):
    nome: str
    argumentos: dict


class RespostaAgente(BaseModel):
    resposta: str
    modelo: str = Field(description="Modelo de IA que respondeu (muda com o fallback entre modelos).")
    ferramentas: list[FerramentaUsada] = Field(description="Consultas feitas para montar a resposta.")
    correcoes: list[str] = Field(description="Trechos corrigidos pela verificação final antes de responder.")


class Fala(BaseModel):
    papel: str = Field(description='"cliente" ou "clave"')
    texto: str


class Historico(BaseModel):
    conversa_id: str
    mensagens: list[Fala]


# ----------------------------------------------------------------------
# Proteção da cota: cada mensagem custa de 1 a 3 chamadas ao modelo
# ----------------------------------------------------------------------
class RateLimiter:
    """Limite por visitante (janela de 60 s) e teto diário somando todos os visitantes.

    Fica na memória do processo: basta para um único container (a demo). Com várias
    réplicas, o contador teria de ir para um lugar compartilhado (ex.: Redis).
    """

    def __init__(self, per_minute: int, per_day: int):
        self.per_minute, self.per_day = per_minute, per_day
        self._hits: dict[str, deque] = defaultdict(deque)
        self._day, self._day_count = date.today(), 0
        self._lock = threading.Lock()  # as rotas rodam em threads: o contador não pode se embaralhar

    def check(self, client: str) -> None:
        now = time.monotonic()
        with self._lock:
            if date.today() != self._day:
                self._day, self._day_count = date.today(), 0
            if self._day_count >= self.per_day:
                raise HTTPException(429, "Limite diário da demonstração atingido. Tente novamente amanhã.")
            hits = self._hits[client]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                raise HTTPException(429, "Muitas mensagens seguidas. Aguarde um minuto.",
                                    headers={"Retry-After": "60"})
            hits.append(now)
            self._day_count += 1


def client_ip(request: Request) -> str:
    """IP do visitante. Atrás de um proxy (ex.: Render), o IP original vem no X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


# ----------------------------------------------------------------------
# Aplicação
# ----------------------------------------------------------------------
def create_app(llm: LLMClient | None = None, store: Store | None = None) -> FastAPI:
    """Monta a API. Os testes passam um LLM simulado; em produção, vem do .env."""
    app = FastAPI(
        title="Clave: Empório da Música",
        description="Agente de atendimento de uma loja de instrumentos musicais (fictícia).",
        version="1.0.0",
    )
    # Carregados uma vez, quando a API liga: ler CSVs e PDF a cada pedido seria lento,
    # e o fallback precisa lembrar entre pedidos quais modelos estão sem cota.
    app.state.store = store or Store()
    app.state.llm = llm or LLMClient(config.get_settings())
    app.state.limiter = RateLimiter(
        per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")),
        per_day=int(os.getenv("RATE_LIMIT_PER_DAY", "300")),
    )
    api_key = os.getenv("API_KEY", "").strip()

    # Dependências: rodam ANTES da rota; se levantarem erro, a rota nem executa.
    def require_key(x_api_key: str | None = Header(default=None)) -> None:
        """Só vale se API_KEY estiver configurada (uso interno). A demo pública fica sem chave."""
        if api_key and not (x_api_key and secrets.compare_digest(x_api_key, api_key)):
            raise HTTPException(401, "Chave de API ausente ou inválida (cabeçalho X-API-Key).")

    def limit(request: Request) -> None:
        app.state.limiter.check(client_ip(request))

    def agent_for(conversa_id: str) -> Agent:
        return Agent(store=app.state.store, llm=app.state.llm, session_id=conversa_id)

    chat_page = CHAT_PAGE.read_text(encoding="utf-8")

    # A tela de chat (front-end) usa a própria API com fetch(): front → API → agente.
    # GET e HEAD: alguns serviços de hospedagem checam se o site está no ar com HEAD.
    @app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
    def chat() -> str:
        return chat_page

    @app.get("/saude", summary="Verifica se o serviço está no ar")
    def saude() -> dict:
        return {"status": "ok"}

    # "def" (e não "async def"): o agente fica esperando o modelo; assim o FastAPI roda
    # cada pedido numa thread e um visitante esperando não trava os outros.
    @app.post("/conversas/{conversa_id}/mensagens", response_model=RespostaAgente,
              summary="Envia uma mensagem e recebe a resposta do Clave",
              dependencies=[Depends(require_key), Depends(limit)])
    def enviar_mensagem(mensagem: MensagemEntrada, conversa_id: str = ConversaId) -> RespostaAgente:
        reply = agent_for(conversa_id).reply(mensagem.texto)
        if reply.model is None:
            # Nenhum modelo respondeu (cota/instabilidade): avisa que dá para tentar de novo.
            raise HTTPException(status_code=503, detail=reply.text)
        return RespostaAgente(
            resposta=reply.text,
            modelo=reply.model,
            ferramentas=[FerramentaUsada(nome=c.name, argumentos=c.arguments) for c in reply.tool_calls],
            correcoes=reply.rewritten,
        )

    @app.get("/conversas/{conversa_id}", response_model=Historico, summary="Histórico visível da conversa",
             dependencies=[Depends(require_key)])
    def historico(conversa_id: str = ConversaId) -> Historico:
        falas = [
            Fala(papel="cliente" if m["role"] == "user" else "clave", texto=m["content"])
            for m in agent_for(conversa_id).history
            # Só o que a cliente vê: as chamadas e os resultados de ferramentas ficam de fora.
            if m.get("role") in ("user", "assistant") and m.get("content") and not m.get("tool_calls")
        ]
        return Historico(conversa_id=conversa_id, mensagens=falas)

    @app.delete("/conversas/{conversa_id}", status_code=204, summary="Apaga a conversa",
                dependencies=[Depends(require_key)])
    def apagar(conversa_id: str = ConversaId) -> None:
        agent_for(conversa_id).reset()

    return app


def main() -> None:
    """Sobe a API com o Uvicorn. Host e porta por variável de ambiente (no container: 0.0.0.0:10000)."""
    import uvicorn

    uvicorn.run(create_app(), host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
