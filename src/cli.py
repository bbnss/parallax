"""CLI entry point for NotizieGeopolitica pipeline."""

import logging
import sys

import click

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


@click.group()
def cli():
    """NotizieGeopolitica — Global News, Multiple Perspectives."""
    pass


@cli.command()
@click.option("--skip-scrape", is_flag=True, help="Skip full-text extraction (faster, for testing)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def collect(skip_scrape, verbose):
    """Collect articles from all RSS feeds."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    from src.collector.feeds import collect_all
    from src.db import get_article_count_by_source

    click.echo("Starting collection...")
    stats = collect_all(skip_scrape=skip_scrape)

    click.echo(f"\nCollection complete:")
    click.echo(f"  New articles: {stats['total_new']}")
    click.echo(f"  Sources OK:   {stats['sources_ok']}")
    click.echo(f"  Sources failed: {stats['sources_failed']}")

    if stats["sources_failed"] > 0:
        click.echo("\nFailed sources:")
        for d in stats["details"]:
            if "error" in d:
                click.echo(f"  - {d['name']}: {d['error']}", err=True)

    click.echo("\nArticle counts per source (active only):")
    rows = get_article_count_by_source()
    current_region = None
    for row in rows:
        # Only show active sources
        if "active" in row.keys() and not row["active"]:
            continue
        if row["region"] != current_region:
            current_region = row["region"]
            click.echo(f"\n  [{current_region.upper()}]")
        click.echo(f"    {row['name']:<25} {row['count']:>5} articles")


@cli.command()
def status():
    """Show current database status."""
    from src.db import init_db, get_article_count_by_source, get_connection

    init_db()

    with get_connection() as conn:
        total_articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        total_sources = conn.execute("SELECT COUNT(*) FROM sources WHERE active=1").fetchone()[0]
        total_clusters = conn.execute("SELECT COUNT(*) FROM story_clusters").fetchone()[0]
        total_comparisons = conn.execute("SELECT COUNT(*) FROM comparisons").fetchone()[0]
        unprocessed = conn.execute("SELECT COUNT(*) FROM articles WHERE processed=0").fetchone()[0]

    click.echo("NotizieGeopolitica — Database Status")
    click.echo("=" * 40)
    click.echo(f"  Active sources:    {total_sources}")
    click.echo(f"  Total articles:    {total_articles}")
    click.echo(f"  Unprocessed:       {unprocessed}")
    click.echo(f"  Story clusters:    {total_clusters}")
    click.echo(f"  Comparisons:       {total_comparisons}")

    click.echo("\nArticles per source:")
    rows = get_article_count_by_source()
    current_region = None
    for row in rows:
        if "active" in row.keys() and not row["active"]:
            continue
        if row["region"] != current_region:
            current_region = row["region"]
            click.echo(f"\n  [{current_region.upper()}]")
        click.echo(f"    {row['name']:<25} {row['count']:>5}")


@cli.command()
@click.option("--limit", default=None, type=int, help="Max articles to summarize (default: all)")
@click.option("--skip-matching", is_flag=True, help="Only summarize, skip story matching")
@click.option("--skip-compare", is_flag=True, help="Skip comparison generation")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def analyze(limit, skip_matching, skip_compare, verbose):
    """Analyze articles: summarize, match stories, generate comparisons."""
    import time
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    from src.analyzer.ollama_client import is_available, get_token_stats, reset_token_stats
    from src.analyzer.summarizer import process_unprocessed_articles
    from src.analyzer.matcher import run_matching
    from src.analyzer.comparator import process_unpublished_clusters

    if not is_available():
        click.echo("ERROR: Ollama is not running or model not available.", err=True)
        click.echo(f"Start Ollama and ensure model '{__import__('src.config', fromlist=['OLLAMA_MODEL']).OLLAMA_MODEL}' is pulled.", err=True)
        raise SystemExit(1)

    # Reset token counters at start of pipeline
    reset_token_stats()

    t0 = time.time()

    # Step 1: Summarize
    click.echo("Step 1/3: Summarizing articles...")
    sum_stats = process_unprocessed_articles(limit=limit)
    elapsed = time.time() - t0
    tokens = get_token_stats()
    click.echo(
        f"  Done: {sum_stats['processed']} summarized, {sum_stats['failed']} failed "
        f"({elapsed:.0f}s) — LLM: {tokens['calls']} calls, "
        f"{tokens['total_tokens']:,} tokens"
    )

    if skip_matching:
        click.echo("Skipping matching and comparison (--skip-matching).")
        _print_token_summary(t0)
        return

    # Step 2: Match stories (NO LLM — only embeddings)
    click.echo("\nStep 2/3: Matching stories across sources (embedding only, no LLM)...")
    t1 = time.time()
    match_stats = run_matching()
    elapsed = time.time() - t1
    click.echo(
        f"  Done: {match_stats['pairs']} pairs confirmed, "
        f"{match_stats['clusters']} new clusters ({elapsed:.0f}s, zero LLM calls)"
    )

    if skip_compare:
        click.echo("Skipping comparison generation (--skip-compare).")
        _print_token_summary(t0)
        return

    # Step 3: Generate comparisons
    click.echo("\nStep 3/3: Generating perspective comparisons...")
    t2 = time.time()
    tokens_before = get_token_stats()
    comp_stats = process_unpublished_clusters()
    elapsed = time.time() - t2
    tokens_after = get_token_stats()
    comp_tokens = tokens_after["total_tokens"] - tokens_before["total_tokens"]
    comp_calls = tokens_after["calls"] - tokens_before["calls"]
    click.echo(
        f"  Done: {comp_stats['generated']} generated, {comp_stats['skipped']} skipped, "
        f"{comp_stats['failed']} failed ({elapsed:.0f}s) — "
        f"LLM: {comp_calls} calls, {comp_tokens:,} tokens"
    )

    _print_token_summary(t0)


def _print_token_summary(t0):
    """Print final token usage summary."""
    import time
    from src.analyzer.ollama_client import get_token_stats

    total_elapsed = time.time() - t0
    tokens = get_token_stats()

    click.echo(f"\n{'='*50}")
    click.echo(f"Analysis complete in {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")
    click.echo(f"{'='*50}")
    click.echo(f"  LLM calls:        {tokens['calls']:>8,}")
    click.echo(f"  Prompt tokens:     {tokens['prompt_tokens']:>8,}")
    click.echo(f"  Completion tokens: {tokens['completion_tokens']:>8,}")
    click.echo(f"  Total tokens:      {tokens['total_tokens']:>8,}")
    click.echo(f"  LLM errors:        {tokens['errors']:>8}")
    if tokens['calls'] > 0:
        avg_ms = tokens['total_duration_ms'] / tokens['calls']
        tps = tokens['completion_tokens'] / (tokens['total_duration_ms'] / 1000) if tokens['total_duration_ms'] > 0 else 0
        click.echo(f"  Avg latency:       {avg_ms:>7,.0f}ms/call")
        click.echo(f"  Throughput:        {tps:>8,.1f} tok/s")
    click.echo(f"{'='*50}")


if __name__ == "__main__":
    cli()
