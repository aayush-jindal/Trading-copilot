"""CLI entry point for the PDF strategy pipeline.

Usage:
    python -m tools.pdf_strategy_pipeline.run <command> [options]

Commands:
    extract   --pdf PATH [--output PATH]
    list      [--strategies PATH]
    ideas     --ticker TICKER [--strategies PATH] [--top N]
    pipeline  --pdf PATH --ticker TICKER [--top N]
"""

from __future__ import annotations

import argparse
import sys

from .config import STRATEGIES_FILE


# ── Command handlers ──────────────────────────────────────────────────────────

def cmd_extract(args: argparse.Namespace) -> None:
    from .pdf_reader import read_pdf, chunk_pages
    from .strategy_extractor import extract_strategies_from_chunks
    from .strategy_store import save_strategies

    output = args.output or STRATEGIES_FILE
    print(f"Reading PDF: {args.pdf}")
    pages = read_pdf(args.pdf)
    print(f"  {len(pages)} pages read.")

    chunks = chunk_pages(pages, pages_per_chunk=4)
    print(f"  {len(chunks)} chunks to process.\n")

    strategies = extract_strategies_from_chunks(chunks)
    print(f"\nExtracted {len(strategies)} unique strategies.")
    save_strategies(strategies, output)


def cmd_list(args: argparse.Namespace) -> None:
    from .strategy_store import list_strategies

    path = args.strategies or STRATEGIES_FILE
    list_strategies(path)


def cmd_ideas(args: argparse.Namespace) -> None:
    from .strategy_store import load_strategies
    from .idea_generator import generate_trade_ideas

    path = args.strategies or STRATEGIES_FILE
    strategies = load_strategies(path)
    if not strategies:
        print(f"No strategies found at {path}. Run 'extract' first.")
        sys.exit(1)

    ideas = generate_trade_ideas(args.ticker, strategies, top_n=args.top)
    print(f"\n{'=' * 60}")
    print(f"TRADE IDEAS: {args.ticker.upper()}")
    print('=' * 60)
    print(ideas)


def cmd_pipeline(args: argparse.Namespace) -> None:
    """Extract strategies from PDF then immediately generate ideas — no file persistence."""
    from .pdf_reader import read_pdf, chunk_pages
    from .strategy_extractor import extract_strategies_from_chunks
    from .idea_generator import generate_trade_ideas

    print(f"Reading PDF: {args.pdf}")
    pages = read_pdf(args.pdf)
    chunks = chunk_pages(pages, pages_per_chunk=4)
    print(f"  {len(pages)} pages → {len(chunks)} chunks.\n")

    strategies = extract_strategies_from_chunks(chunks)
    print(f"\nExtracted {len(strategies)} strategies.\n")

    if not strategies:
        print("No strategies extracted. Cannot generate ideas.")
        sys.exit(1)

    ideas = generate_trade_ideas(args.ticker, strategies, top_n=args.top)
    print(f"\n{'=' * 60}")
    print(f"TRADE IDEAS: {args.ticker.upper()}")
    print('=' * 60)
    print(ideas)


# ── Parser ────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.pdf_strategy_pipeline.run",
        description="PDF → strategies → trade ideas pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # extract
    p_extract = sub.add_parser("extract", help="Read PDF and extract strategies")
    p_extract.add_argument("--pdf", required=True, help="Path to PDF file")
    p_extract.add_argument("--output", default=None, help="Output JSON path (default: strategies.json)")

    # list
    p_list = sub.add_parser("list", help="List extracted strategies")
    p_list.add_argument("--strategies", default=None, help="Path to strategies JSON")

    # ideas
    p_ideas = sub.add_parser("ideas", help="Generate trade ideas for a ticker")
    p_ideas.add_argument("--ticker", required=True, help="Stock symbol, e.g. AAPL")
    p_ideas.add_argument("--strategies", default=None, help="Path to strategies JSON")
    p_ideas.add_argument("--top", type=int, default=3, help="Number of top strategies to use (default: 3)")

    # pipeline
    p_pipe = sub.add_parser("pipeline", help="Full run: extract PDF then generate ideas")
    p_pipe.add_argument("--pdf", required=True, help="Path to PDF file")
    p_pipe.add_argument("--ticker", required=True, help="Stock symbol, e.g. AAPL")
    p_pipe.add_argument("--top", type=int, default=3, help="Number of top strategies to use (default: 3)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "extract":  cmd_extract,
        "list":     cmd_list,
        "ideas":    cmd_ideas,
        "pipeline": cmd_pipeline,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
