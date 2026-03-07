"""CLI entry point for the RAG knowledge base tool.

Usage:
    python -m tools.knowledge_base.run <command> [options]

Commands:
    ingest   [--resources PATH]          Index all PDFs in resources/ into pgvector
    status                               Show indexed files and chunk counts
    query    --ticker TICKER [--top-k N] Retrieve relevant passages + generate strategies
"""

from __future__ import annotations

import argparse
import sys

from .config import RESOURCES_DIR


# ── Command handlers ───────────────────────────────────────────────────────────

def cmd_ingest(args: argparse.Namespace) -> None:
    from .pdf_ingester import ingest_all

    resources = args.resources or RESOURCES_DIR
    print(f"Ingesting PDFs from: {resources}\n")
    ingest_all(resources)


def cmd_status(args: argparse.Namespace) -> None:
    from .pdf_ingester import show_status

    show_status()


def cmd_query(args: argparse.Namespace) -> None:
    from .strategy_gen import generate_strategies

    ticker = args.ticker.upper()
    top_k = args.top_k

    print(f"\nQuerying knowledge base for {ticker} (top_k={top_k})…\n")
    result = generate_strategies(ticker, top_k=top_k)

    print(f"\n{'=' * 70}")
    print(f"  KNOWLEDGE-BASED STRATEGIES: {ticker}")
    print('=' * 70)
    print(result)
    print()


# ── Parser ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.knowledge_base.run",
        description="RAG knowledge base: PDF books → pgvector → trading strategies",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Index all PDFs in resources/ into pgvector")
    p_ingest.add_argument(
        "--resources",
        default=None,
        help=f"Path to PDF folder (default: {RESOURCES_DIR})",
    )

    # status
    sub.add_parser("status", help="Show indexed files and chunk counts")

    # query
    p_query = sub.add_parser(
        "query", help="Retrieve relevant book passages and generate strategies for a ticker"
    )
    p_query.add_argument("--ticker", required=True, help="Stock symbol, e.g. AAPL")
    p_query.add_argument(
        "--top-k",
        type=int,
        default=8,
        dest="top_k",
        help="Number of book passages to retrieve (default: 8)",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "ingest": cmd_ingest,
        "status": cmd_status,
        "query":  cmd_query,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
