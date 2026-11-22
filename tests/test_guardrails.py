"""Detecção de afirmações de popularidade na resposta final."""

import pytest

from emporio.guardrails import popularity_claims


@pytest.mark.parametrize("texto", [
    "O Yamaha C40 é muito procurado por quem está iniciando.",
    "Estes dois de nylon fazem bastante sucesso para iniciantes.",
    "É o mais vendido da loja!",
    "Muita gente compra esse modelo.",
    "É o preferido dos estudantes.",
])
def test_detecta_popularidade(texto):
    assert popularity_claims(texto)


@pytest.mark.parametrize("texto", [
    "A descrição diz que ele é ideal para estudantes e iniciantes.",
    "Violões de nylon costumam ser mais confortáveis para quem está começando.",
    "O Takamine GD20 sai por R$ 2.199,00 ou 12x de R$ 183,25.",
    "Esse modelo está esgotado, mas tenho alternativas parecidas.",
])
def test_nao_acusa_texto_fundamentado(texto):
    assert popularity_claims(texto) == []


def test_acao_sem_execucao():
    from emporio.guardrails import unbacked_actions
    assert unbacked_actions("Já registrei. Protocolo: EM-8821-ATRASO", []) == ["EM-8821-ATRASO", "registrei"]
    ok = [("encaminhar_para_humano", '{"protocolo": "EM-20260325-0001"}')]
    assert unbacked_actions("Registrei: protocolo EM-20260325-0001", ok) == []
    assert unbacked_actions("Já encaminhei", [("encaminhar_para_humano", '{"erro": "x"}')]) == ["encaminhei"]
    assert unbacked_actions("Posso encaminhar seu caso para a equipe?", []) == []


ENCAMINHADO = [("encaminhar_para_humano", '{"protocolo": "EM-20260325-0001", "prazo_de_retorno": "até 24 horas úteis"}')]


@pytest.mark.parametrize("texto", [
    "A equipe vai te ligar ainda hoje!",
    "Vamos resolver em uma hora.",
    "Retorno em 2 horas, combinado?",
    "Alguém fala com você em instantes.",
])
def test_detecta_prazo_sem_respaldo(texto):
    from emporio.guardrails import unbacked_deadlines
    assert unbacked_deadlines(texto, ENCAMINHADO)


@pytest.mark.parametrize("texto,ferramentas", [
    ("O retorno é em até 24 horas úteis.", ENCAMINHADO),
    ("Marquei seu caso como urgente; o retorno é em até 24 horas úteis.", ENCAMINHADO),
    ("Dá para passar na loja ainda hoje, até as 18h.", []),  # sem encaminhamento: é informação
])
def test_nao_acusa_prazo_oficial_ou_informacao(texto, ferramentas):
    from emporio.guardrails import unbacked_deadlines
    assert unbacked_deadlines(texto, ferramentas) == []


@pytest.mark.parametrize("texto,codigo", [
    ("O seu protocolo é o **#2026-0325-01** e o prazo é de 24 horas úteis.", "2026-0325-01"),
    ("Gererei o protocolo **#20263852** para você.", "20263852"),
    ("Protocolo: EM-8821-ATRASO", "EM-8821-ATRASO"),
])
def test_protocolo_inventado_em_qualquer_formato(texto, codigo):
    # Casos reais da avaliação (gemini-3.5-flash-lite), sem nenhuma ferramenta chamada.
    from emporio.guardrails import unbacked_actions
    assert codigo in unbacked_actions(texto, [])


def test_protocolo_real_e_texto_sem_codigo_passam():
    from emporio.guardrails import unbacked_actions
    assert unbacked_actions("O seu protocolo é o EM-20260325-0011.", ENCAMINHADO[:0] + [
        ("encaminhar_para_humano", '{"protocolo": "EM-20260325-0011"}')]) == []
    assert unbacked_actions("Posso abrir um protocolo para você?", []) == []


@pytest.mark.parametrize("texto,esperado", [
    # Casos reais da rodada final de encaminhamento (gemini-3.5-flash-lite), sem ferramenta chamada.
    ("Acabei de encaminhar a sua solicitação. O protocolo gerado para o seu atendimento é o **#2026-0325-01**.",
     ["2026-0325-01", "Acabei de encaminhar"]),
    ("Vou registrar o seu caso agora mesmo para que nossa gerência entre em contato com você o mais rápido "
     "possível ainda hoje.", ["ainda hoje"]),
])
def test_variacoes_reais_de_acao_sem_execucao(texto, esperado):
    from emporio.guardrails import unbacked_actions
    assert unbacked_actions(texto, []) == esperado


def test_horario_e_valores_nao_viram_protocolo():
    from emporio.guardrails import unbacked_actions
    texto = "Abrimos às 9h, o protocolo sai na hora e o violão custa R$ 2.199,00."
    assert unbacked_actions(texto, []) == []


def test_vou_registrar_pedindo_contato_e_legitimo():
    from emporio.guardrails import unbacked_actions
    assert unbacked_actions("Vou registrar seu pedido para a equipe. Me passa um telefone para contato?", []) == []
