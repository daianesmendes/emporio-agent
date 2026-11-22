"""Verificação da resposta final antes de ela chegar ao cliente.

Uma regra no prompt ("não atribua fama a um modelo") reduziu, mas não eliminou,
frases como "o Yamaha C40 é muito procurado" — que os dados desmentem (o C40 não
tem nenhuma venda registrada). Aqui a regra vira código: se a resposta afirma
popularidade, o modelo é chamado mais uma vez para reescrevê-la sem isso.
"""

from __future__ import annotations

import re

# Afirmações de popularidade/reputação: os dados da loja não sustentam nenhuma delas.
POPULARITY_PATTERNS = [
    r"muito procurad[oa]s?",
    r"mais procurad[oa]s?",
    r"mais vendid[oa]s?",
    r"campe[aã]o de vendas",
    r"(faz|fazem) (bastante |muito |o maior )?sucesso",
    r"muito populares?",
    r"mais populares?",
    r"queridinh[oa]s?",
    r"best.?sellers?",
    r"sai muito",
    r"muita sa[ií]da",
    r"(todo mundo|muita gente) (usa|compra|procura|escolhe)",
    r"(preferid[oa]s?|favorit[oa]s?) d[oae]s? (clientes|iniciantes|m[uú]sicos|estudantes)",
]
_POPULARITY_RE = re.compile("|".join(POPULARITY_PATTERNS), re.IGNORECASE)

REWRITE_INSTRUCTION = (
    "[Verificação interna — o cliente não vê esta mensagem] Sua última resposta afirma popularidade ou "
    "reputação de um produto ({trechos}). A loja não tem dados que sustentem isso. Reescreva a resposta "
    "inteira mantendo todo o resto (valores, produtos, pergunta final) e, no lugar da popularidade, use só "
    "o que veio das ferramentas (descrição, especificações) ou orientação musical geral. "
    "Responda apenas com o texto para o cliente."
)


def popularity_claims(text: str) -> list[str]:
    """Trechos da resposta que afirmam popularidade/reputação."""
    return [m.group(0) for m in _POPULARITY_RE.finditer(text or "")]


# Ações afirmadas sem execução: protocolo que não veio de ferramenta, ou "registrei/encaminhei"
# sem nenhuma chamada bem-sucedida de encaminhar_para_humano na conversa. A avaliação pegou o
# agente inventando "EM-8821-ATRASO" e dizendo "já registrei" sem ter chamado a ferramenta.
_PROTOCOL_RE = re.compile(r"\bEM-[A-Z0-9][A-Z0-9-]*[A-Z0-9]\b", re.IGNORECASE)
_ACTION_RE = re.compile(
    r"\b(registrei|encaminhei|repassei|acionei|abri (um |o |seu )?(chamado|caso|protocolo|atendimento))\b",
    re.IGNORECASE,
)

ACTION_INSTRUCTION = (
    "[Verificação interna — o cliente não vê esta mensagem] Sua última resposta afirma uma ação ou cita um "
    "protocolo ({trechos}) sem que encaminhar_para_humano tenha sido executada com sucesso. Se o caso precisa "
    "ir para a equipe, chame encaminhar_para_humano agora (sem o campo protocolo) e informe o protocolo que ela "
    "devolver. Se não precisa, reescreva a resposta sem dizer que registrou ou encaminhou. "
    "Responda apenas com o texto para o cliente."
)


def unbacked_actions(text: str, tool_results: list[tuple[str, str]]) -> list[str]:
    """tool_results: (nome, resultado) de todas as ferramentas já executadas na conversa."""
    known = "\n".join(r for _, r in tool_results)
    handoff_ok = any(n == "encaminhar_para_humano" and '"erro"' not in r for n, r in tool_results)
    problems = [code for code in _PROTOCOL_RE.findall(text or "") if code not in known]
    if not handoff_ok:
        problems += [m.group(0) for m in _ACTION_RE.finditer(text or "")]
    return problems
