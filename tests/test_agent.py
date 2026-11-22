"""Testes do loop do agente e do fallback com LLM simulado (sem gastar cota)."""

import json
from types import SimpleNamespace

import openai
import pytest

from emporio import agent as agent_mod
from emporio.agent import FALLBACK_REPLY, Agent
from emporio.config import Settings
from emporio.data import Store
from emporio.llm import LLMClient


def _msg(content=None, tool_calls=None):
    calls = [
        SimpleNamespace(id=f"call_{i}", function=SimpleNamespace(name=n, arguments=json.dumps(a)))
        for i, (n, a) in enumerate(tool_calls or [])
    ]
    dump = {"role": "assistant", "content": content}
    if calls:
        dump["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in calls
        ]
    return SimpleNamespace(
        content=content,
        tool_calls=calls or None,
        model_dump=lambda exclude_none=True: {k: v for k, v in dump.items() if v is not None},
    )


class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, messages, tools):
        self.calls.append(messages)
        return self.script.pop(0), "fake-model"


@pytest.fixture(autouse=True)
def isolated_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setenv("AGENT_NOW", "2026-03-25 14:00")


def test_loop_executa_ferramenta_e_responde():
    llm = FakeLLM([
        _msg(tool_calls=[("detalhes_produto", {"produto": "Takamine GD20"})]),
        _msg("O Takamine GD20 sai por R$ 2.199,00!"),
    ])
    a = Agent(store=Store(), llm=llm)
    reply = a.reply("Quanto custa o Takamine GD20?")

    assert reply.text.startswith("O Takamine")
    assert [c.name for c in reply.tool_calls] == ["detalhes_produto"]
    tool_msg = llm.calls[1][-1]
    assert tool_msg["role"] == "tool" and "2.199,00" in tool_msg["content"]


def test_historico_persistido_entre_sessoes():
    a = Agent(store=Store(), llm=FakeLLM([_msg("Oi! Sou o Clave.")]), session_id="cliente1")
    a.reply("Oi")
    b = Agent(store=Store(), llm=FakeLLM([]), session_id="cliente1")
    assert [m["role"] for m in b.history] == ["user", "assistant"]


def test_teto_de_rodadas_devolve_mensagem_segura():
    loop = [_msg(tool_calls=[("buscar_produtos", {"termo": "violão"})])] * agent_mod.MAX_TOOL_ROUNDS
    reply = Agent(store=Store(), llm=FakeLLM(loop)).reply("violão")
    assert reply.text == FALLBACK_REPLY


def test_fallback_de_modelo_quando_cota_estoura():
    client = LLMClient(Settings(base_url="http://x", api_key="k", models=["m1", "m2"], now_override=""))
    used = []

    def create(model, **kwargs):
        used.append(model)
        if model == "m1":
            # Cria o erro sem depender da biblioteca HTTP interna do SDK.
            err = openai.RateLimitError.__new__(openai.RateLimitError)
            err.message = "quota"
            raise err
        return SimpleNamespace(choices=[SimpleNamespace(message="ok")])

    client.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    msg, model = client.chat([], [])
    assert (msg, model) == ("ok", "m2")
    # m1 fica em espera: a próxima chamada já vai direto para m2.
    client.chat([], [])
    assert used == ["m1", "m2", "m2"]


def test_fallback_para_provedor_de_reserva_com_historico_limpo():
    from emporio.config import Provider

    reserva = Provider("reserva", "http://y", "k2", ["r1"])
    client = LLMClient(Settings(base_url="http://x", api_key="k", models=["m1"], now_override="", fallback=reserva))
    sent = {}

    def principal(model, **kwargs):
        err = openai.RateLimitError.__new__(openai.RateLimitError)
        err.message = "quota"
        raise err

    def secundario(model, messages, **kwargs):
        sent["messages"] = messages
        return SimpleNamespace(choices=[SimpleNamespace(message="ok")])

    client.clients["principal"] = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=principal)))
    client.clients["reserva"] = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=secundario)))

    historico = [{
        "role": "assistant", "content": None, "extra_content": {"google": {"thought_signature": "abc"}},
        "tool_calls": [{"id": "c1", "type": "function", "extra_content": {"x": 1},
                        "function": {"name": "buscar_produtos", "arguments": "{}"}}],
    }]
    assert client.chat(historico, []) == ("ok", "r1")
    # Campos específicos do Gemini não vão para o outro provedor.
    msg = sent["messages"][0]
    assert "extra_content" not in msg and "extra_content" not in msg["tool_calls"][0]


def test_resposta_com_popularidade_e_reescrita_sem_ir_para_o_historico():
    llm = FakeLLM([
        _msg("O Yamaha C40 é muito procurado por iniciantes!"),
        _msg("O Yamaha C40 tem cordas de nylon, mais macias para quem está começando."),
    ])
    a = Agent(store=Store(), llm=llm)
    reply = a.reply("Qual violão você indica pra iniciante?")

    assert "procurado" not in reply.text
    assert reply.rewritten == ["muito procurado"]
    assert "Verificação interna" in llm.calls[1][-1]["content"]
    # O histórico guarda só a versão final, sem a instrução interna.
    assert all("Verificação interna" not in (m.get("content") or "") for m in a.history)
    assert a.history[-1]["content"] == reply.text


def test_reescrita_que_falha_mantem_resposta_original():
    llm = FakeLLM([
        _msg("O Yamaha C40 é muito procurado!"),
        _msg("O Yamaha C40 é o mais vendido!"),
    ])
    reply = Agent(store=Store(), llm=llm).reply("Qual violão você indica?")
    assert reply.text == "O Yamaha C40 é muito procurado!"
    assert reply.rewritten == []


@pytest.fixture
def handoff_file(tmp_path, monkeypatch):
    from emporio import tools
    path = tmp_path / "atendimentos.jsonl"
    monkeypatch.setattr(tools, "HANDOFF_FILE", path)
    return path


def test_protocolo_inventado_faz_o_agente_chamar_a_ferramenta(handoff_file):
    # Caso real da avaliação: "já registrei", protocolo EM-8821-ATRASO, nenhuma ferramenta chamada.
    llm = FakeLLM([
        _msg("Já registrei o seu caso. Protocolo: EM-8821-ATRASO"),
        _msg(tool_calls=[("encaminhar_para_humano", {"motivo": "reclamacao", "resumo": "Pedido 8 atrasado"})]),
        _msg("Registrei seu caso com o protocolo EM-20260325-0001. Retorno em até 24 horas úteis."),
    ])
    a = Agent(store=Store(), llm=llm)
    reply = a.reply("Meu pedido está atrasado!")

    assert "EM-20260325-0001" in reply.text and "8821" not in reply.text
    assert [c.name for c in reply.tool_calls] == ["encaminhar_para_humano"]
    assert handoff_file.exists()
    assert "EM-8821-ATRASO" in reply.rewritten
    # Histórico coerente: pergunta → chamada da ferramenta → resultado → resposta corrigida.
    assert [m["role"] for m in a.history] == ["user", "assistant", "tool", "assistant"]
    assert all("Verificação interna" not in (m.get("content") or "") for m in a.history)


def test_promessa_sem_acao_pode_virar_resposta_sem_afirmar(handoff_file):
    llm = FakeLLM([
        _msg("Já encaminhei para a gerência!"),
        _msg("Posso encaminhar seu caso para a equipe. Me passa um telefone para contato?"),
    ])
    reply = Agent(store=Store(), llm=llm).reply("Quero falar com o gerente")
    assert reply.text.startswith("Posso encaminhar")
    assert not handoff_file.exists()


def test_reescrita_de_popularidade_nao_executa_ferramentas(handoff_file):
    llm = FakeLLM([
        _msg("O Yamaha C40 é muito procurado!"),
        _msg(tool_calls=[("encaminhar_para_humano", {"motivo": "reclamacao", "resumo": "x"})]),
    ])
    reply = Agent(store=Store(), llm=llm).reply("Qual violão?")
    assert reply.text == "O Yamaha C40 é muito procurado!"
    assert not handoff_file.exists()


def test_prazo_prometido_apos_encaminhar_e_reescrito(handoff_file):
    # Caso real da comparação de modelos: protocolo certo, mas "retorno ainda hoje" contra "até 24 horas úteis".
    llm = FakeLLM([
        _msg(tool_calls=[("encaminhar_para_humano", {"motivo": "reclamacao", "resumo": "Atraso no pedido 8"})]),
        _msg("Protocolo EM-20260325-0001. A equipe te liga ainda hoje!"),
        _msg("Protocolo EM-20260325-0001. Registrei a urgência; o retorno é em até 24 horas úteis."),
    ])
    reply = Agent(store=Store(), llm=llm).reply("Quero que resolvam isso hoje")
    assert "ainda hoje" not in reply.text and "24 horas úteis" in reply.text
    assert reply.rewritten == ["ainda hoje"]


def test_chave_invalida_pula_o_provedor_inteiro(caplog):
    # Caso real do deploy no Render: chave do Gemini colada errada → os 4 modelos devolviam 400,
    # em toda chamada, antes de o Groq responder.
    from emporio.config import Provider

    reserva = Provider("reserva", "http://y", "k2", ["r1"])
    client = LLMClient(Settings(base_url="http://x", api_key="k", models=["m1", "m2", "m3"],
                                now_override="", fallback=reserva))
    tried = []

    def principal(model, **kwargs):
        tried.append(model)
        err = openai.BadRequestError.__new__(openai.BadRequestError)
        err.message = "API key not valid. Please pass a valid API key."
        raise err

    client.clients["principal"] = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=principal)))
    client.clients["reserva"] = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda model, **kw: SimpleNamespace(choices=[SimpleNamespace(message="ok")]))))

    assert client.chat([], []) == ("ok", "r1")
    assert client.chat([], []) == ("ok", "r1")
    assert tried == ["m1"]  # um modelo basta para saber que a chave é inválida; depois o provedor é pulado
    assert "Chave inválida no provedor principal (API key not valid" in caplog.text


def test_400_comum_continua_tentando_o_proximo_modelo():
    client = LLMClient(Settings(base_url="http://x", api_key="k", models=["m1", "m2"], now_override=""))

    def create(model, **kwargs):
        if model == "m1":
            err = openai.BadRequestError.__new__(openai.BadRequestError)
            err.message = "Invalid value for tool_calls"
            raise err
        return SimpleNamespace(choices=[SimpleNamespace(message="ok")])

    client.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert client.chat([], []) == ("ok", "m2")
