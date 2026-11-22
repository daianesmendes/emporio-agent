"""Interface de linha de comando.

  uv run emporio                         # conversa interativa
  uv run emporio --debug                 # mostra as ferramentas chamadas
  uv run emporio --sessao maria          # retoma/salva o histórico "maria"
  uv run emporio --roteiro x.txt -o x.md # roda um roteiro e grava a transcrição
  uv run emporio --roteiro x.txt --svg x.svg  # grava a saída do terminal como imagem
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from . import config
from .agent import Agent, AgentReply
from .prompts import ASSISTANT_NAME

console = Console()


def _print_reply(reply: AgentReply, debug: bool) -> None:
    if debug:
        for c in reply.tool_calls:
            console.print(f"  [dim]⚙ {c.name}({json.dumps(c.arguments, ensure_ascii=False)})[/dim]")
        if reply.rewritten:
            console.print(f"  [dim]🛡 reescrita: removido {', '.join(reply.rewritten)}[/dim]")
        console.print(f"  [dim]modelo: {reply.model}[/dim]")
    console.print(f"[bold magenta]{ASSISTANT_NAME}:[/bold magenta]")
    console.print(Markdown(reply.text))
    console.print()


def interactive(agent: Agent, debug: bool) -> None:
    console.print(f"[bold]🎸 Empório da Música — atendimento com {ASSISTANT_NAME}[/bold]")
    console.print("[dim]Digite sua mensagem. Comandos: /novo (limpa a conversa), /sair[/dim]\n")
    while True:
        try:
            text = console.input("[bold cyan]Você:[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text == "/sair":
            break
        if text == "/novo":
            agent.reset()
            console.print("[dim]Conversa reiniciada.[/dim]\n")
            continue
        with console.status("digitando..."):
            reply = agent.reply(text)
        _print_reply(reply, debug)


def run_script(agent: Agent, script: Path, output: Path | None, pause: float) -> None:
    """Executa um roteiro (uma mensagem por linha; '#' = título/comentário) e grava em Markdown."""
    lines = script.read_text(encoding="utf-8").splitlines()
    title = next((l.lstrip("# ").strip() for l in lines if l.startswith("#")), script.stem)
    messages = [l.strip() for l in lines if l.strip() and not l.startswith("#")]

    md = [f"# {title}", "", f"_Data/hora simulada do atendimento: {config.now():%d/%m/%Y %H:%M}_", ""]
    for i, text in enumerate(messages):
        if i:
            time.sleep(pause)  # respeita o limite de requisições por minuto do plano gratuito
        console.print(f"[bold cyan]Você:[/bold cyan] {text}")
        reply = agent.reply(text)
        _print_reply(reply, debug=True)
        md += [f"**Cliente:** {text}", ""]
        if reply.tool_calls:
            md.append("<details><summary>🔧 Ferramentas consultadas</summary>\n")
            for c in reply.tool_calls:
                md.append(f"- `{c.name}({json.dumps(c.arguments, ensure_ascii=False)})`")
            md += ["", "</details>", ""]
        md += [f"**{ASSISTANT_NAME}:** {reply.text}", ""]
        if reply.rewritten:
            md += [f"<sub>🛡 verificação final reescreveu a resposta para remover: {', '.join(reply.rewritten)}</sub>", ""]
        md += [f"<sub>modelo: {reply.model}</sub>", "", "---", ""]

    if output:
        output.write_text("\n".join(md), encoding="utf-8")
        console.print(f"[green]Transcrição salva em {output}[/green]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente de atendimento da Empório da Música")
    parser.add_argument("--debug", action="store_true", help="mostra ferramentas chamadas e modelo usado")
    parser.add_argument("--sessao", help="nome da sessão para salvar/retomar o histórico")
    parser.add_argument("--roteiro", type=Path, help="arquivo .txt com uma mensagem por linha")
    parser.add_argument("-o", "--saida", type=Path, help="arquivo .md para a transcrição do roteiro")
    parser.add_argument("--svg", type=Path, help="grava a saída do terminal do roteiro como imagem SVG")
    parser.add_argument("--pausa", type=float, default=13.0, help="segundos entre mensagens do roteiro")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s")
    try:
        agent = Agent(session_id=args.sessao)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    if args.roteiro:
        console.record = bool(args.svg)
        run_script(agent, args.roteiro, args.saida, args.pausa)
        if args.svg:
            console.save_svg(str(args.svg), title="uv run emporio --debug")
            console.print(f"[green]Imagem salva em {args.svg}[/green]")
    else:
        interactive(agent, args.debug)


if __name__ == "__main__":
    main()
