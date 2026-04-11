"""menu.py — Rich-based interactive menus for Bedrock model selection."""

import glob
import os
import re

from rich.console import Console
from rich.markdown import Markdown
from rich.rule import Rule
from rich.table import Table

import catalog as cat
import listing as lst
from output import RESULTS_DIR
from listing import SIZE_ORDER
from bedrock_tui_helpers.params import GoBack, GoHome, GoExit

console = Console()

# ---------------------------------------------------------------------------
# Navigation signals — imported from the shared package so the same exception
# classes propagate through both menu.py and params.py ask_* functions.
# ---------------------------------------------------------------------------
# GoBack, GoHome, GoExit are defined in bedrock_tui_helpers.params


# ---------------------------------------------------------------------------
# Core input helper — every prompt goes through here
# ---------------------------------------------------------------------------

def _ask(
    prompt_text: str,
    valid: list[str] | None = None,
    default: str | None = None,
    has_back: bool = True,
    freeform: bool = False,
) -> str:
    """
    Print prompt_text and read a line.
    Always honours:  b=back  h=home  x=exit
    If valid is given, rejects any value not in the list (case-insensitive).
    If freeform=True, any non-empty non-nav value is accepted as-is.
    """
    nav_parts: list[str] = []
    if has_back:
        nav_parts.append("[bold]b[/bold]=back")
    nav_parts.append("[bold]h[/bold]=home")
    nav_parts.append("[bold]x[/bold]=exit")
    nav_hint = "  [dim]" + "  │  ".join(nav_parts) + "[/dim]"

    display = f"\n{prompt_text}{nav_hint}"
    if default:
        display += f"  [dim][{default}][/dim]"
    display += ": "

    while True:
        raw = console.input(display).strip()
        low = raw.lower()

        if low == "b":
            if has_back:
                raise GoBack()
            raise GoHome()
        if low == "h":
            raise GoHome()
        if low == "x":
            raise GoExit()

        if not raw:
            if default is not None:
                return default
            if freeform:
                return ""
            console.print("[red]Please enter a value.[/red]")
            continue

        if valid is not None and low not in [v.lower() for v in valid]:
            console.print(f"[red]Invalid — choose from: {', '.join(valid)}[/red]")
            continue

        return raw


# ---------------------------------------------------------------------------
# Banner & section helpers
# ---------------------------------------------------------------------------

def _banner() -> None:
    console.print()
    console.print("[bold cyan]╔══════════════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║   Amazon Bedrock Model Comparison Tool       ║[/bold cyan]")
    console.print("[bold cyan]╚══════════════════════════════════════════════╝[/bold cyan]")


def _section(title: str, step: int, total: int = 7) -> None:
    console.print(f"\n[bold underline cyan]Step {step}/{total} — {title}[/bold underline cyan]")


# ---------------------------------------------------------------------------
# Read existing comparison reports
# ---------------------------------------------------------------------------

def _list_reports() -> list[str]:
    """Return paths to existing comparison_*.md files, newest first."""
    pattern = os.path.join(RESULTS_DIR, "comparison_*.md")
    files = glob.glob(pattern)
    files.sort(reverse=True)  # newest first (YYYYMMDD_HHMMSS sorts correctly)
    return files


def _read_existing_reports() -> None:
    """Let the user pick and read an existing comparison report."""
    reports = _list_reports()
    if not reports:
        console.print("\n[yellow]No comparison reports found.[/yellow]  Run a comparison first.")
        return

    console.print(f"\n[bold underline cyan]Existing comparison reports ({len(reports)} found)[/bold underline cyan]")

    table = Table(show_header=True, header_style="bold magenta", show_lines=False)
    table.add_column("#", style="bold cyan", width=4)
    table.add_column("File", min_width=40)
    table.add_column("Date", min_width=20)
    table.add_column("Size", min_width=10, justify="right")

    for i, path in enumerate(reports, 1):
        name = os.path.basename(path)
        # Parse date from filename: comparison_YYYYMMDD_HHMMSS.md
        date_str = name.replace("comparison_", "").replace(".md", "")
        try:
            date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {date_str[9:11]}:{date_str[11:13]}:{date_str[13:15]}"
        except (IndexError, ValueError):
            date_display = "unknown"
        size_kb = os.path.getsize(path) / 1024
        table.add_row(str(i), name, date_display, f"{size_kb:.1f} KB")

    console.print(table)

    while True:
        raw = _ask("Select report to read (or b/h/x)", freeform=True)
        if raw.isdigit() and 1 <= int(raw) <= len(reports):
            path = reports[int(raw) - 1]
            console.print()
            console.print(Rule(f"[bold cyan]{os.path.basename(path)}[/bold cyan]", style="cyan"))
            with open(path, encoding="utf-8") as fh:
                console.print(Markdown(fh.read()))
            console.print()
            return
        console.print(f"[red]Invalid — enter a number between 1 and {len(reports)}.[/red]")


# ---------------------------------------------------------------------------
# Step 1 — Max output tokens
# ---------------------------------------------------------------------------

def choose_max_tokens() -> int:
    _section("Max output tokens per model", step=1, total=7)

    presets = [64, 128, 250, 512, 1024, 2048]

    table = Table(show_header=True, header_style="bold magenta", show_lines=False)
    table.add_column("#",          style="bold cyan", width=4)
    table.add_column("Max tokens", min_width=12)
    table.add_column("Usage",      min_width=40)

    descriptions = [
        "Very short — a sentence or two",
        "Short — a brief paragraph",
        "Default — a few paragraphs",
        "Medium — detailed answer",
        "Long — comprehensive response",
        "Extended — deep-dive analysis",
    ]
    for i, (p, d) in enumerate(zip(presets, descriptions), 1):
        table.add_row(str(i), str(p), d)
    table.add_row("c", "custom", "Enter any number between 1 and 10,000")
    table.add_row("r", "read", "Read an existing comparison report")

    console.print(table)

    valid = [str(i) for i in range(1, len(presets) + 1)] + ["c", "r"]
    raw = _ask("Select token limit", valid=valid, default="3")

    if raw == "r":
        _read_existing_reports()
        raise GoHome()  # return to step 1 after reading

    if raw == "c":
        while True:
            num_raw = _ask("Enter token limit (1–10,000)", freeform=True)
            if num_raw.isdigit() and 1 <= int(num_raw) <= 10000:
                chosen = int(num_raw)
                break
            console.print("[red]Must be a number between 1 and 10,000.[/red]")
    else:
        chosen = presets[int(raw) - 1]

    console.print(f"  → [green]{chosen} tokens[/green]")
    return chosen


# ---------------------------------------------------------------------------
# Step 2 — Sampling parameters
# ---------------------------------------------------------------------------

def _ask_float_param(label: str, lo: float, hi: float) -> float | None:
    """Prompt once for an optional float in [lo, hi].  Empty = skip (return None)."""
    while True:
        raw = _ask(f"{label} [{lo}–{hi}, Enter=skip]", freeform=True, default="skip").strip()
        if raw.lower() == "skip":
            return None
        try:
            val = float(raw)
            if lo <= val <= hi:
                return val
            console.print(f"[red]Must be between {lo} and {hi}.[/red]")
        except ValueError:
            console.print("[red]Must be a number (e.g. 0.7).[/red]")


def choose_sampling_params() -> tuple[float | None, float | None, int | None]:
    """Prompt for temperature, top_p, and top_k.  All are optional (Enter = skip)."""
    _section("Sampling parameters", step=2)

    console.print(
        "  These control how the model picks each next token.\n"
        "  Press [bold]Enter[/bold] at any prompt to skip and use the model's built-in default.\n"
    )

    # ── Temperature ──────────────────────────────────────────────────────────
    console.print(
        "  [bold]Temperature[/bold]  (0.0 – 1.0)\n"
        "  [dim]Controls randomness.  [bold]0.0[/bold] = deterministic / repetitive,"
        "  [bold]1.0[/bold] = creative / varied.[/dim]"
    )
    temperature = _ask_float_param("Temperature", 0.0, 1.0)
    if temperature is None:
        console.print("  → [dim]Temperature: model default[/dim]")
    else:
        console.print(f"  → [green]Temperature: {temperature}[/green]")

    # ── Top P ─────────────────────────────────────────────────────────────────
    console.print(
        "\n  [bold]Top P[/bold]  (0.0 – 1.0)\n"
        "  [dim]Nucleus sampling — only tokens whose cumulative probability reaches"
        " this threshold are considered.  Lower = more focused, higher = more diverse.[/dim]"
    )
    top_p = _ask_float_param("Top P", 0.0, 1.0)
    if top_p is None:
        console.print("  → [dim]Top P: model default[/dim]")
    else:
        console.print(f"  → [green]Top P: {top_p}[/green]")

    # ── Top K ─────────────────────────────────────────────────────────────────
    console.print(
        "\n  [bold]Top K[/bold]  (1 – 500)\n"
        "  [dim]Limits sampling to the K most-likely next tokens.  Lower = safer / repetitive,"
        "  higher = more word variety.  Not all models honour this value.[/dim]"
    )
    top_k: int | None = None
    while True:
        raw = _ask("Top K [1–500, Enter=skip]", freeform=True, default="skip").strip()
        if raw.lower() == "skip":
            break
        if raw.isdigit() and 1 <= int(raw) <= 500:
            top_k = int(raw)
            break
        console.print("[red]Must be a whole number between 1 and 500.[/red]")

    if top_k is None:
        console.print("  → [dim]Top K: model default[/dim]")
    else:
        console.print(f"  → [green]Top K: {top_k}[/green]")

    return temperature, top_p, top_k


# ---------------------------------------------------------------------------
# Step 3 — Optional system prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_EXAMPLE = (
    "You are a concise expert assistant. "
    "Answer in plain English, no markdown, under 150 words."
)


def choose_system_prompt() -> str | None:
    _section("System prompt  (optional)", step=3)
    console.print(
        "  A system prompt sets the AI's persona or constraints for [bold]all[/bold] models.\n"
        "  Leave blank to skip.\n"
    )
    console.print(f"  [dim]Example: {_SYSTEM_PROMPT_EXAMPLE}[/dim]\n")

    raw = _ask("System prompt", freeform=True, has_back=True).strip()
    if not raw:
        console.print("  → [dim]No system prompt (skipped)[/dim]")
        return None
    console.print(f"  → [green]System prompt set ({len(raw)} chars)[/green]")
    return raw


def choose_provider(all_models: list[dict]) -> str | None:
    _section("Provider", step=4)

    providers = lst.providers(all_models)

    table = Table(show_header=True, header_style="bold magenta", show_lines=False)
    table.add_column("#",        style="bold cyan", width=4)
    table.add_column("Provider", min_width=22)
    table.add_column("Models",   min_width=8, justify="right")

    table.add_row("0", "All providers", str(len(all_models)))
    for i, p in enumerate(providers, 1):
        count = sum(1 for m in all_models if m["providerName"] == p)
        table.add_row(str(i), p, str(count))

    console.print(table)
    choices = ["0"] + [str(i + 1) for i in range(len(providers))]
    raw = _ask("Select provider", valid=choices, default="0")

    if raw == "0":
        console.print("  → [green]All providers[/green]")
        return None
    chosen = providers[int(raw) - 1]
    console.print(f"  → [green]{chosen}[/green]")
    return chosen


# ---------------------------------------------------------------------------
# Step 4 — Model size
# ---------------------------------------------------------------------------

def choose_size(all_models: list[dict], provider_filter: str | None, modality: str = "TEXT") -> str | None:
    _section("Model size", step=5)

    # Use only ON_DEMAND models with matching modality so counts match step 4
    subset  = lst.filter_models(all_models, provider=provider_filter, modality=modality)
    summary = lst.sizes_summary(subset)

    size_labels = {
        "XS": "Extra Small  (nano / micro / 1–3B params)",
        "S":  "Small        (7–11B params, haiku-class)",
        "M":  "Medium       (13B / mixtral / sonnet-class)",
        "L":  "Large        (70–90B params, pro-class)",
        "XL": "Extra Large  (100B+ params, opus-class)",
        "?":  "Unknown size",
    }

    def fmt_range(lo: float, hi: float) -> str:
        if lo == 0 and hi == 0:
            return "N/A"
        if lo == hi:
            return f"${lo:.6f}"
        return f"${lo:.6f} – ${hi:.6f}"

    table = Table(show_header=True, header_style="bold magenta", show_lines=False)
    table.add_column("#",           style="bold cyan", width=4)
    table.add_column("Size",        min_width=8)
    table.add_column("Description", min_width=42)
    table.add_column("Models",      min_width=7,  justify="right")
    table.add_column("In $/1k",     min_width=24, justify="right")
    table.add_column("Out $/1k",    min_width=24, justify="right")

    table.add_row("0", "All", "All sizes", str(len(subset)), "—", "—")

    available_sizes: list[str] = []
    for entry in summary:
        sz = entry["size"]
        available_sizes.append(sz)
        table.add_row(
            str(len(available_sizes)),
            f"[bold]{sz}[/bold]",
            size_labels.get(sz, ""),
            str(entry["count"]),
            fmt_range(entry["in_min"], entry["in_max"]),
            fmt_range(entry["out_min"], entry["out_max"]),
        )

    console.print(table)
    choices = ["0"] + [str(i + 1) for i in range(len(available_sizes))]
    raw = _ask("Select size", valid=choices, default="0")

    if raw == "0":
        console.print("  → [green]All sizes[/green]")
        return None
    chosen = available_sizes[int(raw) - 1]
    console.print(f"  → [green]{chosen}  {size_labels.get(chosen, '')}[/green]")
    return chosen


# ---------------------------------------------------------------------------
# Model catalog viewer (used inside Step 4)
# ---------------------------------------------------------------------------

def _show_model_catalog(model: dict) -> None:
    """Save (or reuse) the Bedrock catalog page for a model and print its path."""
    console.print(f"\n[dim]Looking up catalog for [bold]{model['modelName']}[/bold]...[/dim]")
    try:
        filepath, was_cached = cat.get_or_create_catalog(model)
    except Exception as exc:
        console.print(f"[red]Could not fetch catalog: {exc}[/red]")
        return

    if was_cached:
        console.print(f"  [dim](reusing cached file — less than 24 h old)[/dim]")
    else:
        console.print(f"  [dim](fetched fresh from Bedrock API)[/dim]")

    console.print(f"\n  [bold green]Catalog saved →[/bold green] [underline]{filepath}[/underline]\n")


# ---------------------------------------------------------------------------
# Step 4 — Model list & selection
# ---------------------------------------------------------------------------

def choose_models(  # noqa: PLR0913
    all_models: list[dict],
    provider_filter: str | None,
    size_filter: str | None,
    modality: str,
) -> list[dict]:
    _section("Select models to compare", step=6)

    filtered = lst.filter_models(
        all_models,
        provider=provider_filter,
        size=size_filter,
        modality=modality,
    )

    if not filtered:
        console.print(
            "[red]No models match the selected filters.[/red]  "
            "Press [bold]b[/bold] to adjust filters."
        )
        _ask("", valid=[], has_back=True, freeform=True)  # only nav keys accepted
        raise GoBack()

    def _print_models_table() -> None:
        t = Table(
            title=f"Filtered models  ({len(filtered)} found)",
            header_style="bold magenta",
            show_lines=True,
        )
        t.add_column("#",          style="bold cyan", width=4)
        t.add_column("Model Name", min_width=34)
        t.add_column("Model ID",   min_width=44, style="dim")
        t.add_column("Provider",   min_width=14)
        t.add_column("Size",       min_width=6, justify="center")
        t.add_column("In $/1k",    min_width=12, justify="right")
        t.add_column("Out $/1k",   min_width=13, justify="right")
        for i, m in enumerate(filtered, 1):
            in_p  = m["_in_price"]
            out_p = m["_out_price"]
            t.add_row(
                str(i),
                m["modelName"],
                m["modelId"],
                m["providerName"],
                m["_size"],
                f"${in_p:.6f}"  if in_p  else "N/A",
                f"${out_p:.6f}" if out_p else "N/A",
            )
        console.print(t)
        console.print(
            "\n[bold]Selection syntax:[/bold]  "
            "[cyan]2[/cyan]  single  │  "
            "[cyan]1,3[/cyan]  multiple  │  "
            "[cyan]1-5[/cyan]  range  │  "
            "[cyan]1,3-5,7[/cyan]  mixed  │  "
            "[cyan]r <num>[/cyan]  read about a model"
        )

    _print_models_table()

    while True:
        raw = _ask("Your selection", freeform=True)

        # ── "r <num>" — read Bedrock catalog for a model ─────────────────────
        parts = raw.strip().split()
        if parts and parts[0].lower() == "r":
            if len(parts) == 2 and parts[1].isdigit():
                idx = int(parts[1])
                if 1 <= idx <= len(filtered):
                    _show_model_catalog(filtered[idx - 1])
                    _print_models_table()
                    continue
            console.print("[red]Usage:  r <number>   e.g. r 3[/red]")
            continue
        # ─────────────────────────────────────────────────────────────────────

        indices = _parse_selection(raw, len(filtered))
        if indices:
            break
        console.print("[red]Invalid — check numbers are within range.[/red]")

    selected = [filtered[i - 1] for i in indices]
    console.print(f"\n[green]{len(selected)} model(s) selected:[/green]")
    for m in selected:
        console.print(f"  [bold]•[/bold] {m['modelName']}  [dim]({m['modelId']})[/dim]")
    return selected


# ---------------------------------------------------------------------------
# Step 5 — Prompt input
# ---------------------------------------------------------------------------

def enter_prompt() -> str:
    _section("Enter your prompt", step=7)
    prompt = _ask("Prompt", freeform=True)
    console.print(f"\n[dim]Prompt saved. Running comparison...[/dim]")
    return prompt


# ---------------------------------------------------------------------------
# Post-run menu
# ---------------------------------------------------------------------------

def post_run_menu() -> str:
    """Return 'home', 'read', or raise GoExit."""
    console.print("\n[bold cyan]─────────────────────────────────────────[/bold cyan]")
    console.print("[bold]What would you like to do next?[/bold]")
    console.print("  [cyan]1[/cyan]  Run another comparison  (→ Home)")
    console.print("  [cyan]r[/cyan]  Read responses  (clean output, no metadata)")
    console.print("  [cyan]x[/cyan]  Exit")
    raw = _ask("Choice", valid=["1", "r"], default="1", has_back=False)
    if raw == "r":
        return "read"
    return "home"


def print_responses(results: list[dict]) -> None:
    """Print only each model's response text — no cost, no token counts."""
    successful = [r for r in results if not r.get("error")]
    failed     = [r for r in results if r.get("error")]

    console.print()
    console.print(Rule("[bold cyan]Model Responses[/bold cyan]", style="cyan"))

    for r in successful:
        console.print()
        console.print(Rule(
            f"[bold green]{r['model_name']}[/bold green]  "
            f"[dim]{r['provider']}  ·  {r['size']}[/dim]",
            style="green",
        ))
        console.print(Markdown(r["output"]))

    if failed:
        console.print()
        console.print(Rule("[bold red]Failed Models[/bold red]", style="red"))
        for r in failed:
            console.print(f"  [yellow]{r['model_name']}[/yellow]  [red]{r['error'][:120]}[/red]")

    console.print()


# ---------------------------------------------------------------------------
# Full menu flow  (step-based loop with back/home/exit support)
# ---------------------------------------------------------------------------

def run_menu(
    *,
    force_refresh: bool = False,
    refresh_pricing: bool = False,
    refresh_probe: bool = False,
) -> tuple[list[dict], str, str, int, float | None, float | None, int | None, str | None] | tuple[None, ...]:
    """
    Drive the 7-step wizard.

    Parameters
    ----------
    force_refresh:
        Bypass both model-list and pricing caches (``--refresh``).
    refresh_pricing:
        Refresh only the pricing cache (``--refresh-pricing``).
    refresh_probe:
        Force a full model invocability probe (``--refresh-probe``).

    Returns (selected_models, prompt, inference_type, max_tokens, temperature, top_p, top_k, system_prompt)
    or      (None, ...) when the user chooses to exit.
    """
    from bedrock_tui_helpers.probe import ensure_probe  # noqa: PLC0415

    _banner()

    # Auto-probe on first run; no-op if cache is fresh (< 7 days old).
    if refresh_probe:
        console.print("[dim]Refreshing model invocability probe…[/dim]")
    ensure_probe(force=refresh_probe)

    # Refresh pricing if requested (independent of model list)
    if refresh_pricing or force_refresh:
        from bedrock_tui_helpers.pricing import load_pricing  # noqa: PLC0415
        console.print("[dim]Refreshing pricing data from AWS Pricing API…[/dim]")
        load_pricing(force_refresh=True)

    console.print("\n[dim]Fetching available models from Bedrock...[/dim]", end=" ")
    all_models = lst.list_models(force_refresh=force_refresh)
    console.print(f"[green]{len(all_models)} models retrieved.[/green]")

    step: int = 1
    inf_type: str               = "TEXT"
    max_tokens: int             = 250
    temperature: float | None   = None
    top_p: float | None         = None
    top_k: int | None           = None
    system_prompt: str | None   = None
    provider_filter: str | None = None
    size_filter: str | None     = None
    selected: list[dict]        = []

    while True:
        try:
            if step == 1:
                max_tokens = choose_max_tokens()
                step = 2

            elif step == 2:
                temperature, top_p, top_k = choose_sampling_params()
                step = 3

            elif step == 3:
                system_prompt = choose_system_prompt()
                step = 4

            elif step == 4:
                provider_filter = choose_provider(all_models)
                step = 5

            elif step == 5:
                size_filter = choose_size(all_models, provider_filter, inf_type)
                step = 6

            elif step == 6:
                selected = choose_models(all_models, provider_filter, size_filter, inf_type)
                step = 7

            elif step == 7:
                prompt = enter_prompt()
                return selected, prompt, inf_type, max_tokens, temperature, top_p, top_k, system_prompt

        except GoBack:
            step = max(1, step - 1)

        except GoHome:
            # Re-print the banner and restart from step 1, keeping cached models
            _banner()
            console.print(f"\n[dim]{len(all_models)} models already loaded.[/dim]")
            step = 1
            max_tokens = 250
            temperature = None
            top_p = None
            top_k = None
            system_prompt = None
            provider_filter = None
            size_filter = None
            selected = []

        except GoExit:
            return (None,) * 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_selection(selection: str, max_val: int) -> list[int]:
    """Parse '1,3-5,7' into a sorted deduplicated list of 1-based indices."""
    indices: set[int] = set()
    for part in selection.split(","):
        part = part.strip()
        m = re.match(r"^(\d+)-(\d+)$", part)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            if start < 1 or end > max_val or start > end:
                return []
            indices.update(range(start, end + 1))
        elif re.match(r"^\d+$", part):
            val = int(part)
            if val < 1 or val > max_val:
                return []
            indices.add(val)
        else:
            return []
    return sorted(indices)
