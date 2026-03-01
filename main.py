"""ThesisAI — Interactive CLI entry point.

Run:  python main.py
"""

import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

import config
from agent.thesis_ai import ThesisAI

console = Console()

BANNER = r"""
 _____ _               _        _    ___
|_   _| |__   ___  ___(_)___   / \  |_ _|
  | | | '_ \ / _ \/ __| / __| / _ \  | |
  | | | | | |  __/\__ \ \__ \/ ___ \ | |
  |_| |_| |_|\___||___/_|___/_/   \_\___|

  Autonomous Research Assistant
"""

HELP_TEXT = """\
Commands:
  /help      Show this help message
  /reset     Clear conversation (memory persists)
  /memory    Show current memory context
  /topic     Set thesis topic          (e.g. /topic Graph Neural Networks for Drug Discovery)
  /area      Set research area         (e.g. /area deep learning)
  /method    Set chosen methodology    (e.g. /method GCN + attention mechanism)
  /outline   Generate a full thesis outline
  /write     Draft a chapter           (e.g. /write Literature Review)
  /quit      Exit ThesisAI
"""


def print_banner() -> None:
    console.print(Panel(Text(BANNER, style="bold cyan"), border_style="cyan"))


def print_help() -> None:
    console.print(Panel(HELP_TEXT, title="[bold]Help[/bold]", border_style="green"))


def handle_command(cmd: str, agent: ThesisAI) -> bool:
    """Handle slash commands.  Returns True if the command was handled."""
    parts = cmd.strip().split(maxsplit=1)
    keyword = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if keyword == "/help":
        print_help()
        return True

    if keyword == "/quit":
        console.print("[bold yellow]Goodbye! Good luck with your thesis.[/bold yellow]")
        sys.exit(0)

    if keyword == "/reset":
        agent.reset()
        console.print("[green]Conversation cleared. Memory retained.[/green]")
        return True

    if keyword == "/memory":
        ctx = agent.memory.render_context()
        console.print(Panel(ctx, title="[bold]Memory[/bold]", border_style="magenta"))
        return True

    if keyword == "/topic":
        if not arg:
            console.print("[red]Usage: /topic <your thesis topic>[/red]")
        else:
            agent.memory.set_thesis_topic(arg)
            console.print(f"[green]Thesis topic set to:[/green] {arg}")
        return True

    if keyword == "/area":
        if not arg:
            console.print("[red]Usage: /area <research area>[/red]")
        else:
            agent.memory.set_research_area(arg)
            console.print(f"[green]Research area set to:[/green] {arg}")
        return True

    if keyword == "/method":
        if not arg:
            console.print("[red]Usage: /method <methodology>[/red]")
        else:
            agent.memory.set_methodology(arg)
            console.print(f"[green]Methodology set to:[/green] {arg}")
        return True

    if keyword == "/outline":
        topic = arg or agent.memory.data.get("thesis_topic", "")
        if not topic:
            console.print("[red]Set your topic first with /topic <topic>[/red]")
            return True
        prompt = (
            f"Generate a detailed thesis outline for the topic: "
            f"\"{topic}\". Include chapter numbers, titles, section headings, "
            f"and a brief description of what each section should cover."
        )
        _send_to_agent(agent, prompt)
        return True

    if keyword == "/write":
        topic = agent.memory.data.get("thesis_topic", "")
        if not topic:
            console.print("[red]Set your topic first with /topic <topic>[/red]")
            return True
        if not arg:
            console.print(
                "[red]Usage: /write <chapter name>[/red]\n"
                "  Examples: /write Introduction, /write Literature Review, "
                "/write Methodology"
            )
            return True
        prompt = (
            f"Write a detailed first draft for the thesis chapter: "
            f"\"{arg}\" for the thesis topic: \"{topic}\". "
            f"Write in academic style with proper structure, subsections, "
            f"placeholder citations like [AuthorYear], and logical flow. "
            f"Aim for roughly 1500-2000 words."
        )
        _send_to_agent(agent, prompt)
        return True

    return False  # not a known command


def _send_to_agent(agent: ThesisAI, prompt: str) -> None:
    """Send a prompt to the agent and display the response."""
    with console.status("[bold cyan]ThesisAI is writing...[/bold cyan]"):
        try:
            response = agent.chat(prompt)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            return
    console.print()
    console.print(
        Panel(
            Markdown(response),
            title="[bold green]ThesisAI[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )
    console.print()

def main() -> None:
    # ── Preflight checks ────────────────────────────────────────
    if not config.GITHUB_TOKEN:
        console.print(
            "[bold red]Error:[/bold red] GITHUB_TOKEN not set.\n"
            "Get a free token at: https://github.com/settings/tokens\n"
            "Then add it to your .env file."
        )
        sys.exit(1)

    print_banner()
    console.print(
        "[dim]Type [bold]/help[/bold] for commands or just start chatting.[/dim]\n"
    )

    agent = ThesisAI()

    while True:
        try:
            user_input = console.input("[bold blue]You >[/bold blue] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[bold yellow]Goodbye![/bold yellow]")
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            handle_command(user_input, agent)
            continue

        # Normal message → agent loop
        with console.status("[bold cyan]ThesisAI is thinking...[/bold cyan]"):
            try:
                response = agent.chat(user_input)
            except Exception as exc:
                err_msg = str(exc)
                if "insufficient_quota" in err_msg or "429" in err_msg:
                    console.print(
                        "[bold red]Error:[/bold red] OpenAI quota exceeded.\n"
                        "  → Add credits at: https://platform.openai.com/settings/organization/billing\n"
                        "  → Note: API billing is separate from ChatGPT Plus."
                    )
                elif "invalid_api_key" in err_msg or "401" in err_msg:
                    console.print(
                        "[bold red]Error:[/bold red] Invalid API key.\n"
                        "  → Check your key in the .env file."
                    )
                else:
                    console.print(f"[bold red]Error:[/bold red] {exc}")
                continue

        console.print()
        console.print(
            Panel(
                Markdown(response),
                title="[bold green]ThesisAI[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )
        console.print()


if __name__ == "__main__":
    main()
