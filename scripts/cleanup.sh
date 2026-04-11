#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Collect what will be deleted
TO_DELETE=()
[[ -d ".venv" ]]          && TO_DELETE+=(".venv/               (virtual environment)")
[[ -d "results" ]]        && TO_DELETE+=("results/             (comparison reports + model list + restricted-IDs cache)")
[[ -d "catalog" ]]        && TO_DELETE+=("catalog/             (cached model detail pages)")
[[ -d "__pycache__" ]]    && TO_DELETE+=("__pycache__/         (Python bytecode cache)")

if [[ ${#TO_DELETE[@]} -eq 0 ]]; then
    echo "Nothing to clean up — all generated files already absent."
    exit 0
fi

echo ""
echo "The following will be permanently deleted:"
echo ""
for item in "${TO_DELETE[@]}"; do
    echo "  • $item"
done
echo ""
read -r -p "Proceed? [y/N] " confirm
if [[ "${confirm,,}" != "y" ]]; then
    echo "Aborted — nothing deleted."
    exit 0
fi

echo ""
if [[ -d ".venv" ]]; then
    # Deactivate if the venv is currently active in this shell
    if [[ "${VIRTUAL_ENV:-}" == *".venv" ]]; then
        deactivate 2>/dev/null || true
    fi
    rm -rf .venv
    echo "  ✓ Removed .venv/"
fi
[[ -d "results" ]]     && { rm -rf results;     echo "  ✓ Removed results/"; }
[[ -d "catalog" ]]     && { rm -rf catalog;     echo "  ✓ Removed catalog/"; }
[[ -d "__pycache__" ]] && { rm -rf __pycache__; echo "  ✓ Removed __pycache__/"; }

echo ""
echo "Done."
