"""CLI interface for kbase - designed for both human and LLM consumption."""
import json
import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from kbase.store import KBaseStore
from kbase.ingest import ingest_directory, ingest_file
from kbase.search import hybrid_search, semantic_only, keyword_only, sql_search, get_table_context
from kbase.watch import start_watcher

console = Console()


def _output(data: dict, fmt: str):
    """Output results in requested format."""
    if fmt == "json":
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        _pretty_print(data)


def _pretty_print(data: dict):
    """Human-readable output."""
    if "error" in data and data["error"]:
        console.print(f"[red]Error: {data['error']}[/red]")
        return

    if "results" in data and isinstance(data["results"], list):
        console.print(f"\n[bold]Found {data.get('result_count', len(data['results']))} results[/bold]")
        console.print(f"Methods: {', '.join(data.get('methods_used', []))}\n")

        for i, item in enumerate(data["results"], 1):
            meta = item.get("metadata", {})
            score = item.get("rrf_score") or item.get("score", 0)
            console.print(f"[bold cyan]#{i}[/bold cyan] [yellow]{meta.get('file_name', '?')}[/yellow]  "
                          f"[dim](score: {score:.4f})[/dim]")
            console.print(f"  [dim]{meta.get('file_path', '?')}[/dim]")
            text = item.get("text", "")[:300]
            console.print(f"  {text}{'...' if len(item.get('text', '')) > 300 else ''}\n")

        if data.get("table_hint"):
            console.print("[bold yellow]Tip:[/bold yellow] This query may involve tabular data. "
                          "Use `kbase sql` to query tables directly.")

    elif "results" in data and isinstance(data["results"], dict):
        # SQL result
        result = data["results"]
        if result.get("error"):
            console.print(f"[red]SQL Error: {result['error']}[/red]")
        else:
            table = Table()
            for col in result.get("columns", []):
                table.add_column(col)
            for row in result.get("rows", [])[:50]:
                table.add_row(*[str(v) for v in row])
            console.print(table)

    elif "tables" in data:
        # Table context
        for t in data["tables"]:
            console.print(f"\n[bold]{t['table_name']}[/bold] ({t['row_count']} rows)")
            console.print(f"  File: {t['file_path']}")
            console.print(f"  Headers: {', '.join(t['headers'])}")

    elif "file_count" in data:
        # Stats
        table = Table(title="Knowledge Base Stats")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        for k, v in data.items():
            if k == "type_counts":
                for ext, cnt in v.items():
                    table.add_row(f"  {ext}", str(cnt))
            else:
                table.add_row(k, str(v))
        console.print(table)

    else:
        console.print_json(json.dumps(data, ensure_ascii=False, default=str))


@click.group()
@click.option("--workspace", "-w", default="default", help="Workspace name")
@click.option("--format", "-f", "fmt", default="pretty", type=click.Choice(["pretty", "json"]))
@click.pass_context
def main(ctx, workspace, fmt):
    """kbase - Local knowledge base with RAG + Text2SQL + full-text search."""
    ctx.ensure_object(dict)
    ctx.obj["workspace"] = workspace
    ctx.obj["fmt"] = fmt


@main.command()
@click.argument("directory")
@click.option("--force", is_flag=True, help="Re-index all files even if unchanged")
@click.pass_context
def ingest(ctx, directory, force):
    """Ingest files from a directory into the knowledge base."""
    store = KBaseStore(ctx.obj["workspace"])

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Ingesting...", total=None)

        def callback(current, total, name, status):
            progress.update(task, total=total, completed=current,
                            description=f"[{'green' if status == 'processed' else 'dim'}]{name}[/]")

        stats = ingest_directory(store, directory, force=force, progress_callback=callback)

    store.close()
    _output(stats, ctx.obj["fmt"])


@main.command(name="add")
@click.argument("file_path")
@click.option("--force", is_flag=True)
@click.pass_context
def add_file(ctx, file_path, force):
    """Add a single file to the knowledge base."""
    store = KBaseStore(ctx.obj["workspace"])
    result = ingest_file(store, file_path, force=force)
    store.close()
    _output(result, ctx.obj["fmt"])


@main.command()
@click.argument("query")
@click.option("--top-k", "-k", default=10, help="Number of results")
@click.option("--type", "-t", "search_type",
              type=click.Choice(["auto", "semantic", "keyword"]), default="auto")
@click.option("--file-type", help="Filter by file type (e.g. .pptx)")
@click.option("--no-rerank", is_flag=True, help="Disable re-ranking")
@click.option("--no-expand", is_flag=True, help="Disable query expansion")
@click.pass_context
def search(ctx, query, top_k, search_type, file_type, no_rerank, no_expand):
    """Search the knowledge base (with re-ranking + query expansion)."""
    store = KBaseStore(ctx.obj["workspace"])

    if search_type == "semantic":
        result = semantic_only(store, query, top_k=top_k, file_type=file_type)
    elif search_type == "keyword":
        result = keyword_only(store, query, top_k=top_k)
    else:
        result = hybrid_search(store, query, top_k=top_k,
                               use_rerank=not no_rerank, use_expand=not no_expand)

    store.close()
    _output(result, ctx.obj["fmt"])


@main.command()
@click.argument("sql_query")
@click.pass_context
def sql(ctx, sql_query):
    """Execute SQL query on tabular data (from XLSX/CSV files)."""
    store = KBaseStore(ctx.obj["workspace"])
    result = sql_search(store, sql_query)
    store.close()
    _output(result, ctx.obj["fmt"])


@main.command()
@click.pass_context
def tables(ctx):
    """List all indexed tables (from XLSX/CSV) with schemas."""
    store = KBaseStore(ctx.obj["workspace"])
    result = get_table_context(store)
    store.close()
    _output(result, ctx.obj["fmt"])


@main.command()
@click.pass_context
def status(ctx):
    """Show knowledge base statistics."""
    store = KBaseStore(ctx.obj["workspace"])
    stats = store.get_stats()
    store.close()
    _output(stats, ctx.obj["fmt"])


@main.command()
@click.option("--source-dir", help="Filter by source directory")
@click.pass_context
def files(ctx, source_dir):
    """List indexed files."""
    store = KBaseStore(ctx.obj["workspace"])
    file_list = store.list_files(source_dir)
    _output({"files": file_list, "count": len(file_list)}, ctx.obj["fmt"])
    store.close()


@main.command(name="remove")
@click.argument("file_path")
@click.pass_context
def remove_file(ctx, file_path):
    """Remove a file from the knowledge base."""
    store = KBaseStore(ctx.obj["workspace"])
    store.remove_file(file_path)
    store.close()
    console.print(f"[green]Removed: {file_path}[/green]")


@main.command()
@click.argument("question")
@click.option("--provider", "-p", default=None, help="LLM provider (e.g. claude-sonnet, qwen-plus, ollama)")
@click.option("--top-k", "-k", default=10)
@click.pass_context
def chat(ctx, question, provider, top_k):
    """Chat with LLM using knowledge base context."""
    from kbase.chat import chat as do_chat, LLM_PROVIDERS
    from kbase.config import load_settings
    store = KBaseStore(ctx.obj["workspace"])
    settings = load_settings(ctx.obj["workspace"])
    if provider:
        settings["llm_provider"] = provider
    try:
        result = do_chat(store, question, settings=settings, top_k=top_k)
        if ctx.obj["fmt"] == "json":
            _output(result, "json")
        else:
            console.print(f"\n[bold]{result.get('answer', 'No answer')}[/bold]\n")
            if result.get("sources"):
                console.print("[dim]Sources:[/dim]")
                for s in result["sources"][:5]:
                    console.print(f"  [cyan]{s['name']}[/cyan]")
            console.print(f"\n[dim]{result.get('provider','?')} | {result.get('context_chunks',0)} chunks[/dim]")
    finally:
        store.close()


@main.command()
@click.pass_context
def errors(ctx):
    """Show files that failed to index."""
    store = KBaseStore(ctx.obj["workspace"])
    files = store.list_files()
    errs = [f for f in files if f.get("error")]
    store.close()
    if ctx.obj["fmt"] == "json":
        _output({"total": len(errs), "errors": errs}, "json")
    else:
        console.print(f"\n[bold red]{len(errs)} errors[/bold red] out of {len(files)} files\n")
        from collections import Counter
        summary = Counter()
        for f in errs:
            summary[f["error"][:60]] += 1
        for msg, cnt in summary.most_common(15):
            console.print(f"  [red]{cnt:4d}[/red]  {msg}")


@main.command(name="open")
@click.argument("query")
@click.pass_context
def open_file(ctx, query):
    """Search and open the top result file in Finder/Explorer."""
    import subprocess, platform
    store = KBaseStore(ctx.obj["workspace"])
    result = hybrid_search(store, query, top_k=1)
    store.close()
    if result.get("results"):
        fpath = result["results"][0].get("metadata", {}).get("file_path", "")
        if fpath:
            console.print(f"Opening: [cyan]{fpath}[/cyan]")
            system = platform.system()
            if system == "Darwin":
                subprocess.Popen(["open", "-R", fpath])
            elif system == "Windows":
                subprocess.Popen(["explorer", "/select,", fpath])
            else:
                subprocess.Popen(["xdg-open", str(Path(fpath).parent)])
        else:
            console.print("[red]No file path in result[/red]")
    else:
        console.print("[yellow]No results found[/yellow]")


@main.command()
@click.option("--host", default="0.0.0.0")
@click.option("--port", "-p", default=8765)
@click.pass_context
def web(ctx, host, port):
    """Start the web UI and API server."""
    from kbase.web import run_server
    console.print(f"[bold green]Starting KBase Web UI[/bold green] at http://localhost:{port}")
    run_server(workspace=ctx.obj["workspace"], host=host, port=port)


@main.command()
@click.argument("directory")
@click.pass_context
def watch(ctx, directory):
    """Watch a directory and auto-index file changes."""
    store = KBaseStore(ctx.obj["workspace"])
    console.print(f"[bold green]Watching:[/bold green] {directory}")
    console.print("Press Ctrl+C to stop.\n")

    observer = start_watcher(store, directory, log_func=console.print)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        console.print("\n[yellow]Watcher stopped.[/yellow]")
    observer.join()
    store.close()


if __name__ == "__main__":
    main()
