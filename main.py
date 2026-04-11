"""main.py — Orchestrates the Bedrock Model Comparison tool."""

import argparse

import boto3_helpers
from rich.console import Console

from menu import run_menu, post_run_menu, print_responses, GoExit, GoHome
from inference import run_comparison
from output import save_results

console = Console()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive CLI that benchmarks Bedrock foundation models side-by-side."
    )
    parser.add_argument(
        "--region", default="us-west-2",
        help="AWS region (default: us-west-2, overridden by AWS_DEFAULT_REGION)",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Bypass the 24h model-list and pricing caches — fetch fresh from AWS",
    )
    parser.add_argument(
        "--refresh-pricing", action="store_true",
        help="Refresh only the pricing cache (keeps the model list cache)",
    )
    parser.add_argument(
        "--refresh-probe", action="store_true",
        help="Force a full model invocability probe even if the cache exists",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # Set the AWS region once for the whole process.
    boto3_helpers.configure(region=args.region)

    while True:
        try:
            selected_models, prompt, inference_type, max_tokens, temperature, top_p, top_k, system_prompt = run_menu(
                force_refresh=args.refresh,
                refresh_pricing=args.refresh_pricing,
                refresh_probe=args.refresh_probe,
            )
        except GoExit:
            _goodbye()
            return

        # After first run, don't re-refresh on subsequent wizard loops
        args.refresh = False
        args.refresh_pricing = False
        args.refresh_probe = False

        # run_menu() returns (None, ...) when user exits via 'x'
        if selected_models is None:
            _goodbye()
            return

        results = run_comparison(selected_models, prompt, inference_type, max_tokens, temperature, top_p, top_k, system_prompt)

        if results:
            filepath = save_results(prompt, results, inference_type)
            console.print(
                f"\n[bold green]✓ Results saved →[/bold green] "
                f"[underline]{filepath}[/underline]"
            )

        # Ask whether to run another comparison, read responses, or exit
        while True:
            try:
                action = post_run_menu()
            except GoExit:
                _goodbye()
                return
            except GoHome:
                break  # restart the wizard

            if action == "read":
                print_responses(results)
                continue  # show the menu again after reading
            break  # action == "home" → loop back to run_menu()


def _goodbye() -> None:
    console.print(
        "\n[bold cyan]Thanks for using Bedrock Model Compare. Goodbye![/bold cyan]\n"
    )


if __name__ == "__main__":
    main()
