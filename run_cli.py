"""CLI entry point for StudyTips AI Agent.

Interactive REPL loop for processing agent prompts from the terminal.
"""

from __future__ import annotations

import sys
import os

# Ensure the project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

console = Console()

HELP_TEXT = """
## Available Commands

- **Any natural language prompt** — e.g. "Write a blog post about study tips"
- **/login** — Connect to GitHub Copilot via browser device-flow (like VS Code)
- **/logout** — Disconnect GitHub Copilot
- **/audit** — Run a site health check
- **/report** — Generate daily report
- **/pending** — Show pending actions
- **/topics** — Get topic suggestions
- **/health** — Quick site health check
- **/crawl** — Deep-crawl the entire site (pages, drafts, orphans, broken links)
- **/autolink** — Auto-insert internal links into all draft posts
- **/navfix** — Place drafts under correct parent pages in navigation
- **/missing** — Find broken internal links and create missing pages
- **/design** — Run a full design & performance review
- **/powerfix** — One-click auto-fix: autolink + navfix + missing pages
- **/help** — Show this help
- **/quit** or **/exit** — Exit the agent
"""


def print_welcome() -> None:
    """Print the welcome banner."""
    console.print(
        Panel.fit(
            "[bold cyan]StudyTips AI Agent[/bold cyan]\n"
            "[dim]Autonomous WordPress management for studytips.in[/dim]\n\n"
            "[green]Type a prompt or /help for commands[/green]",
            border_style="cyan",
        )
    )


def handle_result(result: dict, agent: object) -> None:
    """Display result and handle approve/reject workflow.

    Args:
        result: Agent result dict from process_prompt.
        agent: StudyTipsAgent instance.
    """
    # Display formatted output
    console.print()
    formatted = result.get("formatted_output", "No output")
    try:
        console.print(Markdown(formatted))
    except Exception:  # noqa: BLE001
        console.print(formatted)

    console.print()
    choice = Prompt.ask(
        "[bold]Action[/bold]",
        choices=["a", "r", "e", "s"],
        default="s",
        show_choices=True,
        show_default=True,
        console=console,
    )
    console.print(
        "[dim]a=approve, r=reject, e=edit feedback, s=skip[/dim]"
    )

    if choice == "a":
        try:
            agent.execute_approved(result)
            console.print("[bold green]✅ Approved and executed![/bold green]")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[bold red]❌ Execution failed: {exc}[/bold red]")
    elif choice == "r":
        feedback = Prompt.ask("Feedback (optional)", default="", console=console)
        agent.learn_from_rejection(result, feedback=feedback)
        console.print("[yellow]❌ Rejected. Agent will learn from this.[/yellow]")
    elif choice == "e":
        feedback = Prompt.ask("Edit/feedback notes", console=console)
        agent.learn_from_rejection(result, feedback=feedback)
        console.print("[yellow]📝 Feedback recorded. You can re-run the prompt.[/yellow]")
    else:
        console.print("[dim]Skipped — action saved as pending.[/dim]")


def main() -> None:
    """Main CLI loop."""
    print_welcome()

    try:
        from agent.core.orchestrator import StudyTipsAgent
    except ImportError as exc:
        console.print(f"[red]Import error: {exc}\nRun: pip install -r requirements.txt[/red]")
        sys.exit(1)

    agent = StudyTipsAgent()
    console.print("[dim]Agent initialised. Memory DB: " + agent.config.agent.memory_db_path + "[/dim]\n")

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]You[/bold cyan]", console=console).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        # Built-in commands
        if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
            console.print("[dim]Goodbye![/dim]")
            break

        if user_input.lower() in ("/help", "help"):
            console.print(Markdown(HELP_TEXT))
            continue

        if user_input.lower() == "/login":
            try:
                from agent.integrations.copilot_auth import interactive_login
                interactive_login(open_browser=True)
                console.print("[bold green]✅ GitHub Copilot connected![/bold green]")
            except KeyboardInterrupt:
                console.print("\n[yellow]Login cancelled.[/yellow]")
            except Exception as exc:
                console.print(f"[bold red]Login failed: {exc}[/bold red]")
            continue

        if user_input.lower() == "/logout":
            import os as _os
            _os.environ.pop("GITHUB_COPILOT_TOKEN", None)
            try:
                from agent.integrations.copilot_auth import _token_manager, ENV_FILE
                _token_manager.invalidate()
                if ENV_FILE.exists():
                    _lines = ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
                    ENV_FILE.write_text(
                        "".join(l for l in _lines if not l.startswith("GITHUB_COPILOT_TOKEN=")),
                        encoding="utf-8",
                    )
            except Exception:
                pass
            console.print("[yellow]Disconnected from GitHub Copilot.[/yellow]")
            continue

        if user_input.lower() in ("/health", "/audit"):
            with console.status("Running site health check..."):
                health = agent.check_site_health()
            console.print(Panel(
                f"Score: {health.get('score', 'N/A')}/100\n"
                f"Critical: {len(health.get('critical', []))}\n"
                f"Warnings: {len(health.get('warnings', []))}\n"
                f"Good: {len(health.get('good', []))}",
                title="Site Health",
                border_style="green",
            ))
            continue

        if user_input.lower() == "/report":
            report = agent.generate_daily_report()
            console.print(Markdown(report))
            continue

        if user_input.lower() == "/pending":
            pending = agent.get_pending_actions()
            if not pending:
                console.print("[green]No pending actions.[/green]")
            else:
                console.print(f"[yellow]{len(pending)} pending actions:[/yellow]")
                for action in pending[:5]:
                    console.print(f"  • [{action['intent']}] ID:{action['action_id']}")
            continue

        if user_input.lower() == "/topics":
            with console.status("Fetching topic suggestions..."):
                from agent.core.brain_router import BrainRouter
                from agent.modules.content_engine import ContentEngine
                brain = BrainRouter(config=agent.config)
                engine = ContentEngine(brain_router=brain, config=agent.config)
                topics = engine.suggest_topics(count=5)
            console.print("\n[bold]Topic Suggestions:[/bold]")
            for topic in topics:
                console.print(f"  • {topic}")
            continue

        # ── Power-tool shortcuts ──────────────────────────────
        if user_input.lower() in ("/crawl", "/autolink", "/navfix", "/missing", "/design", "/powerfix"):
            from agent.modules.site_power import SitePower
            from agent.core.brain_router import BrainRouter
            brain = BrainRouter(config=agent.config)
            sp = SitePower(brain_router=brain, config=agent.config)
            cmd = user_input.lower().lstrip("/")
            try:
                if cmd == "crawl":
                    with console.status("[cyan]Deep-crawling studytips.in...[/cyan]"):
                        data = sp.deep_crawl()
                    console.print(Panel(
                        f"Pages: {data['total_pages']}  Posts: {data['total_posts']}  Drafts: {data['total_drafts']}\n"
                        f"Orphan pages: {len(data.get('orphan_pages', []))}  Missing targets: {len(data.get('missing_targets', []))}",
                        title="🕷️ Deep Crawl", border_style="cyan",
                    ))
                elif cmd == "autolink":
                    with console.status("[cyan]Auto-linking drafts...[/cyan]"):
                        data = sp.auto_link_drafts()
                    console.print(f"[green]✅ Linked {data.get('linked', 0)} drafts ({data.get('links_added', 0)} links added)[/green]")
                elif cmd == "navfix":
                    with console.status("[cyan]Placing drafts in navigation...[/cyan]"):
                        data = sp.place_drafts_in_nav()
                    console.print(f"[green]✅ Placed {data.get('placed', 0)} draft pages under correct parents[/green]")
                elif cmd == "missing":
                    with console.status("[cyan]Finding & creating missing pages...[/cyan]"):
                        data = sp.create_missing_pages()
                    console.print(f"[green]✅ Created {data.get('created', 0)} missing pages as drafts[/green]")
                elif cmd == "design":
                    with console.status("[cyan]Analysing design & performance...[/cyan]"):
                        data = sp.analyze_design()
                    console.print(Markdown(data.get("llm_review", "No review generated.")))
                elif cmd == "powerfix":
                    with console.status("[cyan]Running full auto-fix pipeline...[/cyan]"):
                        data = sp.auto_fix_all()
                    console.print(Panel(
                        f"Links added: {data.get('auto_link', {}).get('links_added', 0)}\n"
                        f"Drafts placed: {data.get('nav_placement', {}).get('placed', 0)}\n"
                        f"Pages created: {data.get('missing_pages', {}).get('created', 0)}",
                        title="⚡ Auto-Fix Complete", border_style="green",
                    ))
            except Exception as exc:
                console.print(f"[bold red]❌ {cmd} failed: {exc}[/bold red]")
            continue

        # Process as agent prompt
        with console.status(f"[cyan]Processing: {user_input[:60]}...[/cyan]"):
            try:
                result = agent.process_prompt(user_input)
            except Exception as exc:  # noqa: BLE001
                console.print(f"[bold red]Error: {exc}[/bold red]")
                continue

        handle_result(result, agent)


if __name__ == "__main__":
    main()
