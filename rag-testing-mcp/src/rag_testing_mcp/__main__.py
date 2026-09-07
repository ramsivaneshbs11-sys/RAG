"""
CLI entry point for rag-testing-mcp.

Usage:
    python -m rag_testing_mcp health
    python -m rag_testing_mcp query "What is cultural ecology?"
    python -m rag_testing_mcp evaluate evaluation/dataset.json
    python -m rag_testing_mcp compare --a http://localhost:8000 --b http://localhost:8001 --dataset evaluation/dataset.json
    python -m rag_testing_mcp serve     # start MCP server (stdio)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


def _run_health():
    from rag_testing_mcp.clients.rag_client import RAGClient
    from rag_testing_mcp.config import get_settings

    async def _do():
        client = RAGClient(get_settings())
        result = await client.health_check()
        await client.close()
        print(json.dumps(result, indent=2))

    asyncio.run(_do())


def _run_query(question: str, mode: str = "prelims"):
    from rag_testing_mcp.clients.rag_client import RAGClient
    from rag_testing_mcp.config import get_settings

    async def _do():
        client = RAGClient(get_settings())
        resp = await client.run_query(question, mode=mode)
        await client.close()
        print(json.dumps(resp.model_dump(), indent=2, default=str))

    asyncio.run(_do())


def _run_evaluate(dataset_path: str):
    from rag_testing_mcp.config import get_settings
    from rag_testing_mcp.runners.dataset import run_dataset
    from rag_testing_mcp.reporting.json_report import save_json_report
    from rag_testing_mcp.reporting.csv_report import save_csv_report
    from rag_testing_mcp.reporting.html_report import save_html_report

    async def _do():
        settings = get_settings()
        run = await run_dataset(settings, dataset_path)
        results_dir = settings.results_dir
        jp = save_json_report(run, results_dir)
        cp = save_csv_report(run, results_dir)
        hp = save_html_report(run, results_dir)
        print(f"Evaluation complete: {run.successful}/{run.total_questions} passed")
        print(f"  Failures: {len(run.failures)}")
        print(f"  Reports:  {jp}  |  {cp}  |  {hp}")

    asyncio.run(_do())


def _run_compare(url_a: str, url_b: str, dataset_path: str):
    from rag_testing_mcp.config import get_settings
    from rag_testing_mcp.runners.comparison import compare_versions

    async def _do():
        settings = get_settings()
        result = await compare_versions(settings, url_a, url_b, dataset_path)
        print(json.dumps(result.summary, indent=2, default=str))

    asyncio.run(_do())


def _run_serve():
    from rag_testing_mcp.server import main
    main()


def cli():
    parser = argparse.ArgumentParser(
        prog="rag_testing_mcp",
        description="RAG Testing MCP — Evaluate, benchmark, and audit RAG applications",
    )
    sub = parser.add_subparsers(dest="command")

    # health
    sub.add_parser("health", help="Check if the RAG API is running")

    # query
    q = sub.add_parser("query", help="Run one question against the RAG")
    q.add_argument("question", type=str)
    q.add_argument("--mode", default="prelims")

    # evaluate
    e = sub.add_parser("evaluate", help="Run a full evaluation dataset")
    e.add_argument("dataset", type=str)

    # compare
    c = sub.add_parser("compare", help="Compare two RAG versions")
    c.add_argument("--a", required=True, dest="url_a")
    c.add_argument("--b", required=True, dest="url_b")
    c.add_argument("--dataset", required=True)

    # serve (MCP stdio)
    sub.add_parser("serve", help="Start the MCP server (stdio transport)")

    args = parser.parse_args()

    if args.command == "health":
        _run_health()
    elif args.command == "query":
        _run_query(args.question, args.mode)
    elif args.command == "evaluate":
        _run_evaluate(args.dataset)
    elif args.command == "compare":
        _run_compare(args.url_a, args.url_b, args.dataset)
    elif args.command == "serve":
        _run_serve()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    cli()
