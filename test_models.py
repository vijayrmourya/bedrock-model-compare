"""test_models.py — Probe every Bedrock model to find which are invocable.

Delegates all probe logic to ``bedrock_tui_helpers.probe``, which stores the
canonical results in the shared package cache
(``bedrock_tui_helpers/.probe_results.json``).  That cache is used
automatically by every downstream project to filter out inaccessible models.

After running, a human-readable copy is also written to
``results/disabled.json`` for review.

Usage
-----
    # activate the project venv first
    source .venv/bin/activate

    python test_models.py
    python test_models.py --region eu-central-1
    python test_models.py --refresh        # bypass the 24h model-list cache
    python test_models.py --workers 10     # run up to 10 concurrent probes
"""

from __future__ import annotations

import argparse
import json
import os
import time

import boto3_helpers
from rich.console import Console
from rich.table import Table
from rich import box

from bedrock_tui_helpers.models import streaming_text_models
import bedrock_tui_helpers.probe as probe

console = Console()

# Human-readable copy written under results/ for local review
_RESULTS_DIR   = os.path.join(os.path.dirname(__file__), "results")
_DISABLED_FILE = os.path.join(_RESULTS_DIR, "disabled.json")


def _on_result(r: dict) -> None:
    """Print live progress for each completed probe."""
    status = "[bold green]✓[/bold green]" if r["ok"] else "[bold red]✗[/bold red]"
    console.print(
        f"  {status}  {r['provider']:<16} {r['name']:<40} "
        f"[dim]{r['latency_ms']:.0f} ms[/dim]"
        + (f"  [red]{r['error'][:60]}[/red]" if r["error"] else "")
    )


def _save_local_copy(results: list[dict]) -> tuple[list[str], list[str]]:
    """Write a human-readable copy to results/disabled.json."""
    ok_ids       = [r["model_id"] for r in results if r["ok"]]
    disabled_ids = [r["model_id"] for r in results if not r["ok"]]
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_probed": len(results),
        "ok": len(ok_ids),
        "disabled_count": len(disabled_ids),
        "disabled": sorted(disabled_ids),
        "errors": {
            r["model_id"]: r["error"]
            for r in results if not r["ok"]
        },
    }
    with open(_DISABLED_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return ok_ids, disabled_ids


def _print_summary(results: list[dict], disabled_ids: list[str]) -> None:
    ok     = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]

    console.print()
    t = Table(
        title="Model probe summary",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    t.add_column("Status",   width=8,  justify="center")
    t.add_column("Provider", min_width=14)
    t.add_column("Model",    min_width=32)
    t.add_column("Invoke ID", style="dim", min_width=40)
    t.add_column("Response / Error", min_width=40)

    for r in sorted(results, key=lambda x: (not x["ok"], x["provider"], x["name"])):
        invoke_id = r.get("invoke_id", r["model_id"])
        if r["ok"]:
            t.add_row(
                "[green]✓ OK[/green]",
                r["provider"],
                r["name"],
                invoke_id,
                f'[dim]{r["response"]}[/dim]',
            )
        else:
            t.add_row(
                "[red]✗ FAIL[/red]",
                r["provider"],
                r["name"],
                invoke_id,
                f'[red]{(r["error"] or "")[:60]}[/red]',
            )

    console.print(t)
    console.print(
        f"\n[bold]Probe complete:[/bold]  "
        f"[green]{len(ok)} invocable[/green]  "
        f"[red]{len(failed)} disabled[/red]  "
        f"out of {len(results)} models"
    )
    if disabled_ids:
        console.print(
            f"\n[bold yellow]results/disabled.json[/bold yellow] written — "
            f"{len(disabled_ids)} inaccessible model(s) will be hidden "
            f"automatically on the next run."
        )
    else:
        console.print("\n[green]All models are invocable.[/green]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe every Bedrock foundation model with a one-turn prompt."
    )
    parser.add_argument("--region", default="us-west-2", help="AWS region (default: us-west-2)")
    parser.add_argument("--refresh", action="store_true", help="Bypass the 24h model-list and pricing caches")
    parser.add_argument("--refresh-pricing", action="store_true", help="Refresh only the pricing cache")
    parser.add_argument("--workers", type=int, default=5, metavar="N",
                        help="Concurrent probes (default: 5)")
    args = parser.parse_args()

    boto3_helpers.configure(region=args.region)

    # Refresh pricing if requested
    if args.refresh or args.refresh_pricing:
        from bedrock_tui_helpers.pricing import load_pricing
        console.print("[dim]Refreshing pricing data from AWS Pricing API…[/dim]")
        load_pricing(force_refresh=True)

    console.print("[bold cyan]bedrock-model-compare — Model invocability probe[/bold cyan]")
    console.print(f"  Region  : {args.region}")
    console.print(f"  Prompt  : \"{probe._PROBE_PROMPT}\"")
    console.print(f"  Workers : {args.workers}\n")

    console.print("[dim]Fetching model list…[/dim]")
    # streaming_text_models with skip_disabled_filter=True returns the full
    # undeduplicated list — we want to probe all models, not just enabled ones.
    models = streaming_text_models(
        region=args.region,
        force_refresh=args.refresh,
        skip_disabled_filter=True,
    )
    console.print(f"[dim]{len(models)} models found.  Starting probes…[/dim]\n")

    results = probe.run_probe(models, workers=args.workers, on_result=_on_result)
    _, disabled_ids = _save_local_copy(results)
    _print_summary(results, disabled_ids)


if __name__ == "__main__":
    main()
