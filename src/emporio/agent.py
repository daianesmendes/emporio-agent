"""Loop do agente: LLM decide, ferramentas executam, LLM responde."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .data import Store
from .guardrails import (ACTION_INSTRUCTION, DEADLINE_INSTRUCTION, REWRITE_INSTRUCTION, SAFE_ACTION_REPLY,
                         drop_sentences, popularity_claims, unbacked_actions, unbacked_deadlines)
from .llm import AllModelsUnavailable, LLMClient
from .prompts import build_system_prompt
from .tools import run_tool, tool_schemas

log = logging.getLogger(__name__)

SESSIONS_DIR = Path(__file__).resolve().parents[2] / ".sessions"
MAX_TOOL_ROUNDS = 4       # teto de idas e voltas por mensagem (protege a cota)
MAX_HISTORY_MESSAGES = 40  # histórico enviado ao modelo

FALLBACK_REPLY = (
    "Opa, tive um probleminha técnico aqui e não consegui consultar o sistema agora. "
    "Você pode tentar de novo em instantes ou falar com a equipe pelo (67) 3341-4444?"
)


@dataclass
class ToolCall:
    name: str
    arguments: dict
    result: str


@dataclass
class AgentReply:
    text: str
    model: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    rewritten: list[str] = field(default_factory=list)  # trechos removidos pela verificação final


def _trim(history: list[dict]) -> list[dict]:
    """Mantém as mensagens mais recentes, sempre começando numa mensagem do usuário
    (cortar no meio de uma chamada de ferramenta quebra a conversa para o modelo)."""
    if len(history) <= MAX_HISTORY_MESSAGES:
        return history
    cut = len(history) - MAX_HISTORY_MESSAGES
    while cut < len(history) and history[cut].get("role") != "user":
        cut += 1
    return history[cut:]


class Agent:
    def __init__(self, store: Store | None = None, llm: LLMClient | None = None, session_id: str | None = None):
        self.store = store or Store()
        self.llm = llm or LLMClient(config.get_settings())
        self.tools = tool_schemas(self.store)
        self.session_id = session_id
        self.history: list[dict] = self._load() if session_id else []

    # --- persistência ---------------------------------------------------
    def _path(self) -> Path:
        return SESSIONS_DIR / f"{self.session_id}.json"

    def _load(self) -> list[dict]:
        path = self._path()
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def _save(self) -> None:
        if not self.session_id:
            return
        SESSIONS_DIR.mkdir(exist_ok=True)
        self._path().write_text(json.dumps(self.history, ensure_ascii=False, indent=1), encoding="utf-8")

    def reset(self) -> None:
        self.history = []
        self._save()

    # --- conversa -------------------------------------------------------
    def _complete(self, system: dict, messages: list[dict], calls: list[ToolCall], rounds: int,
                  run_tools: bool = True):
        """Roda o loop modelo → ferramentas até uma resposta final. Devolve (mensagens novas, modelo),
        ou (mensagens, None) se estourar o teto de rodadas."""
        new: list[dict] = []
        model = None
        for _ in range(rounds):
            msg, model = self.llm.chat([system, *_trim(self.history), *messages, *new], self.tools)
            # exclude_none preserva campos extras do provedor (ex.: assinaturas
            # de "pensamento" do Gemini) que precisam voltar na próxima chamada.
            new.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                return new, model
            if not run_tools:
                return new, None
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = run_tool(self.store, tc.function.name, args)
                calls.append(ToolCall(tc.function.name, args, result))
                new.append({"role": "tool", "tool_call_id": tc.id, "content": result})
        return new, None

    def _tool_results(self, messages: list[dict]) -> list[tuple[str, str]]:
        """(nome, resultado) de cada ferramenta executada nas mensagens dadas."""
        names = {tc["id"]: tc["function"]["name"]
                 for m in messages for tc in (m.get("tool_calls") or [])}
        return [(names.get(m.get("tool_call_id"), ""), m.get("content") or "")
                for m in messages if m.get("role") == "tool"]

    def reply(self, user_text: str) -> AgentReply:
        system = {"role": "system", "content": build_system_prompt(self.store, config.now())}
        turn: list[dict] = [{"role": "user", "content": user_text}]
        calls: list[ToolCall] = []
        rewritten: list[str] = []

        try:
            new, model = self._complete(system, turn, calls, MAX_TOOL_ROUNDS)
            turn += new
            if model is None:
                log.warning("Teto de %d rodadas atingido.", MAX_TOOL_ROUNDS)
                turn.append({"role": "assistant", "content": FALLBACK_REPLY})
            text = (turn[-1].get("content") or "").strip() or FALLBACK_REPLY

            # Verificação final 1: ação ou protocolo sem execução. A correção pode chamar a ferramenta.
            problems = unbacked_actions(text, self._tool_results(self.history + turn))
            if problems and model:
                fixed = self._correct(system, turn, calls, ACTION_INSTRUCTION, problems,
                                      lambda t, msgs: unbacked_actions(t, self._tool_results(self.history + msgs)))
                if fixed:
                    turn, text, model = fixed
                # Plano B: se ainda sobrou ação ou protocolo sem execução (a correção falhou, ou chamou a
                # ferramenta mas manteve o protocolo falso), a resposta vira a mensagem segura.
                if unbacked_actions(text, self._tool_results(self.history + turn)):
                    text = self._replace_final(turn, SAFE_ACTION_REPLY)
                rewritten += problems

            # Verificação final 2: prazo prometido diferente do oficial. Só reescreve o texto.
            deadlines = unbacked_deadlines(text, self._tool_results(self.history + turn))
            if deadlines and model:
                fixed = self._correct(system, turn, calls, DEADLINE_INSTRUCTION, deadlines,
                                      lambda t, msgs: unbacked_deadlines(t, self._tool_results(self.history + msgs)),
                                      allow_tools=False)
                if fixed:
                    turn, text, model = fixed
                else:
                    # Plano B: tira só as frases com o prazo prometido; o protocolo e o resto continuam.
                    text = self._replace_final(turn, drop_sentences(text, deadlines) or SAFE_ACTION_REPLY)
                rewritten += deadlines

            # Verificação final 3: popularidade sem dado. Só reescreve o texto.
            claims = popularity_claims(text)
            if claims and model:
                fixed = self._correct(system, turn, calls, REWRITE_INSTRUCTION, claims,
                                      lambda t, msgs: popularity_claims(t), allow_tools=False)
                if fixed:
                    turn, text, model = fixed
                    rewritten += claims
                else:
                    # Plano B: tira só as frases com popularidade, se sobrar uma resposta.
                    trimmed = drop_sentences(text, claims)
                    if trimmed:
                        text = self._replace_final(turn, trimmed)
                        rewritten += claims
        except AllModelsUnavailable as e:
            log.error("Nenhum modelo disponível: %s", e)
            return AgentReply(FALLBACK_REPLY, None, calls)

        self.history.extend(turn)
        self._save()
        return AgentReply(text, model, calls, rewritten)

    @staticmethod
    def _replace_final(turn: list[dict], text: str) -> str:
        """Troca o texto da resposta final do turno (o histórico guarda só a versão entregue)."""
        turn[-1] = {"role": "assistant", "content": text}
        return text

    def _correct(self, system, turn, calls, instruction, problems, still_bad, allow_tools=True):
        """Mostra ao modelo a resposta problemática com uma instrução interna e pede outra versão.
        A instrução e a resposta problemática não entram no histórico: fica só a versão corrigida
        (e as ferramentas que ela chamou). Devolve (turno, texto, modelo) ou None se não melhorou."""
        nudge = {"role": "user", "content": instruction.format(trechos=", ".join(f'"{p}"' for p in problems))}
        base = turn[:-1]
        new_calls: list[ToolCall] = []
        new, model = self._complete(system, [*turn, nudge], new_calls, 2 if allow_tools else 1, run_tools=allow_tools)
        text = (new[-1].get("content") or "").strip() if new else ""
        if model is None or not text:
            log.warning("Correção não produziu resposta final: %s", problems)
            return None
        fixed_turn = base + new
        # Se a correção executou uma ferramenta (ex.: abriu o caso de verdade), o histórico precisa registrá-la.
        # Só vale a correção que resolveu tudo: "melhorou um pouco" ainda leva o problema ao cliente.
        # Se chamou ferramenta, a versão fica (o histórico precisa da chamada) e o plano B confere o texto.
        if not new_calls and still_bad(text, fixed_turn):
            log.warning("Correção não resolveu: %s", problems)
            return None
        calls += new_calls
        return fixed_turn, text, model
