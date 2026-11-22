"""Testes da API com o TestClient do FastAPI e um LLM simulado (sem gastar cota).

O caminho testado é o completo: pedido HTTP → API → Agent.reply() → resposta JSON.
"""

import pytest
from fastapi.testclient import TestClient

from emporio import agent as agent_mod
from emporio.api import create_app
from emporio.data import Store
from emporio.llm import AllModelsUnavailable

from test_agent import FakeLLM, _msg

STORE = Store()  # carregar CSVs e PDF uma vez para todos os testes


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setenv("AGENT_NOW", "2026-03-25 14:00")
    monkeypatch.delenv("API_KEY", raising=False)


def client_with(script) -> TestClient:
    return TestClient(create_app(llm=FakeLLM(script), store=STORE))


def test_saude():
    assert client_with([]).get("/saude").json() == {"status": "ok"}


def test_mensagem_devolve_resposta_ferramentas_e_modelo():
    client = client_with([
        _msg(tool_calls=[("detalhes_produto", {"produto": "Takamine GD20"})]),
        _msg("O Takamine GD20 sai por R$ 2.199,00."),
    ])
    r = client.post("/conversas/maria/mensagens", json={"texto": "Quanto custa o Takamine GD20?"})
    assert r.status_code == 200
    body = r.json()
    assert body["resposta"] == "O Takamine GD20 sai por R$ 2.199,00."
    assert body["modelo"] == "fake-model"
    assert body["ferramentas"] == [{"nome": "detalhes_produto", "argumentos": {"produto": "Takamine GD20"}}]
    assert body["correcoes"] == []


def test_historico_mostra_so_as_falas_e_delete_apaga():
    client = client_with([
        _msg(tool_calls=[("detalhes_produto", {"produto": "Takamine GD20"})]),
        _msg("Sai por R$ 2.199,00."),
    ])
    client.post("/conversas/maria/mensagens", json={"texto": "Quanto custa o Takamine?"})

    falas = client.get("/conversas/maria").json()["mensagens"]
    assert falas == [{"papel": "cliente", "texto": "Quanto custa o Takamine?"},
                     {"papel": "clave", "texto": "Sai por R$ 2.199,00."}]  # sem chamadas nem resultados de ferramentas

    assert client.delete("/conversas/maria").status_code == 204
    assert client.get("/conversas/maria").json()["mensagens"] == []


def test_conversas_sao_separadas_por_id():
    client = client_with([_msg("Oi, Maria!"), _msg("Oi, João!")])
    client.post("/conversas/maria/mensagens", json={"texto": "oi"})
    client.post("/conversas/joao/mensagens", json={"texto": "oi"})
    assert client.get("/conversas/maria").json()["mensagens"][-1]["texto"] == "Oi, Maria!"
    assert client.get("/conversas/joao").json()["mensagens"][-1]["texto"] == "Oi, João!"


@pytest.mark.parametrize("conversa_id", ["..", "a.b", "com espaço", "x" * 65, "%2E%2E%2F.env"])
def test_id_invalido_e_recusado(conversa_id):
    # O id vira nome de arquivo: nada de pontos, barras ou espaços (path traversal).
    r = client_with([]).get(f"/conversas/{conversa_id}")
    assert r.status_code in (404, 422)


@pytest.mark.parametrize("texto", ["", "x" * 1001])
def test_texto_vazio_ou_longo_demais_e_recusado(texto):
    assert client_with([]).post("/conversas/maria/mensagens", json={"texto": texto}).status_code == 422


def test_formato_errado_e_recusado():
    r = client_with([]).post("/conversas/maria/mensagens", json={"txt": "oi"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "texto"]  # o FastAPI diz exatamente o que faltou


def test_modelo_indisponivel_devolve_503():
    class DownLLM:
        def chat(self, messages, tools):
            raise AllModelsUnavailable("sem cota")

    client = TestClient(create_app(llm=DownLLM(), store=STORE))
    r = client.post("/conversas/maria/mensagens", json={"texto": "oi"})
    assert r.status_code == 503
    assert "tentar de novo" in r.json()["detail"]


def test_limite_por_visitante(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    client = client_with([_msg("1"), _msg("2"), _msg("3")])
    ana = {"X-Forwarded-For": "1.1.1.1"}
    assert client.post("/conversas/a/mensagens", json={"texto": "oi"}, headers=ana).status_code == 200
    assert client.post("/conversas/a/mensagens", json={"texto": "oi"}, headers=ana).status_code == 200
    bloqueado = client.post("/conversas/a/mensagens", json={"texto": "oi"}, headers=ana)
    assert bloqueado.status_code == 429 and bloqueado.headers["Retry-After"] == "60"
    # Outro visitante (outro IP) tem o próprio limite.
    outro = client.post("/conversas/b/mensagens", json={"texto": "oi"}, headers={"X-Forwarded-For": "2.2.2.2"})
    assert outro.status_code == 200


def test_teto_diario_somando_todos(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_DAY", "2")
    client = client_with([_msg("1"), _msg("2")])
    for ip in ("1.1.1.1", "2.2.2.2"):
        assert client.post("/conversas/a/mensagens", json={"texto": "oi"},
                           headers={"X-Forwarded-For": ip}).status_code == 200
    r = client.post("/conversas/a/mensagens", json={"texto": "oi"}, headers={"X-Forwarded-For": "3.3.3.3"})
    assert r.status_code == 429 and "diário" in r.json()["detail"]


def test_chave_de_api_quando_configurada(monkeypatch):
    monkeypatch.setenv("API_KEY", "segredo-de-teste")
    client = client_with([_msg("Oi!")])
    assert client.post("/conversas/a/mensagens", json={"texto": "oi"}).status_code == 401
    assert client.get("/conversas/a", headers={"X-API-Key": "errada"}).status_code == 401
    ok = client.post("/conversas/a/mensagens", json={"texto": "oi"}, headers={"X-API-Key": "segredo-de-teste"})
    assert ok.status_code == 200
    assert client.get("/saude").status_code == 200  # a verificação de saúde nunca exige chave
