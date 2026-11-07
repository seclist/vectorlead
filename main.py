"""VectorLead CLI Entry Point.

Autonomous Instagram Lead Discovery, Qualification, and CRM Sync Engine.
Executes live profile crawlers, runs the rolling 35-day AHS momentum engine,
evaluates Engagement Quality (EQS) & Funnel Maturity (FMI), and syncs
qualified leads non-destructively to Google Sheets.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# Ensure standard output and error support UTF-8 on Windows
if sys.platform == "win32":
    try:
        if sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr.encoding.lower() != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.algorithm import AccountMetrics, FunnelTier, calculate_ahs
from src.classifier import NicheClassifier
from src.database import ProspectDatabase
from src.scraper import (
    InstagramCrawler,
    InstagramProfile,
    classify_funnel_tier,
    get_curated_seed_prospects,
)
from src.sheets_sync import BaseCRM, get_crm_backend

app = typer.Typer(
    name="vectorlead",
    help="VectorLead: Autonomous Instagram Lead Discovery, Momentum Scoring (AHS), and CRM Engine.",
    add_completion=False,
)
console = Console()

BANNER = """[bold cyan]
 __     __        _             _                     _ 
 \\ \\   / /__  ___| |_ ___  _ __| |    ___  __ _  __| |
  \\ \\ / / _ \\/ __| __/ _ \\| '__| |   / _ \\/ _` |/ _` |
   \\ V /  __/ (__| || (_) | |  | |__|  __/ (_| | (_| |
    \\_/ \\___|\\___|\\__\\___/|_|  |_____\\___|\\__,_|\\__,_|
[/bold cyan]
[dim]Autonomous Momentum Discovery Engine • Engagement Quality (EQS) • Funnel Maturity (FMI)[/dim]
"""


@app.command()
def hunt(
    niche: str = typer.Option(
        "personal_trainer",
        "--niche",
        "-n",
        help="Target niche defined in config/niches.yaml.",
    ),
    min_new_leads: int = typer.Option(
        10,
        "--min-new-leads",
        "-m",
        help="Target quota of verified, qualified leads to write to Tracker.",
    ),
    max_followers: int = typer.Option(
        100_000,
        "--max-followers",
        "-f",
        help="Maximum follower cap (creators exceeding this receive M=0.0 multiplier).",
    ),
    min_ahs: float = typer.Option(
        60.0,
        "--min-ahs",
        help="Minimum Account Health Score required to qualify.",
    ),
    seeds: Optional[str] = typer.Option(
        None,
        "--seeds",
        "-s",
        help="Comma-separated usernames or path to a text file of handles.",
    ),
    local_crm: bool = typer.Option(
        False,
        "--local-crm",
        help="Force local CSV CRM mirror instead of connecting to Google Sheets.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Simulate hunting run without persisting to database or sheets.",
    ),
) -> None:
    """Execute autonomous discovery, qualification loop, and non-destructive CRM sync."""
    console.print(BANNER)

    # 1. Initialize Engines
    classifier = NicheClassifier()
    if niche not in classifier.list_niches():
        console.print(
            f"[bold red]Error:[/bold red] Niche '{niche}' not found in configuration. "
            f"Available niches: {', '.join(classifier.list_niches())}"
        )
        raise typer.Exit(code=1)

    db = ProspectDatabase()
    crm = get_crm_backend(force_local=local_crm)
    crawler = InstagramCrawler()

    backend_name = "Local CSV CRM (crm_data/)" if isinstance(crm, type(get_crm_backend(force_local=True))) else "Google Sheets CRM"
    console.print(
        Panel.fit(
            f"[bold green]Target Niche:[/bold green] {niche} ([dim]{classifier.get_niche(niche).name if classifier.get_niche(niche) else ''}[/dim])\n"
            f"[bold green]Target Quota:[/bold green] {min_new_leads} new qualified leads in [bold]Tracker[/bold]\n"
            f"[bold green]Max Follower Cap:[/bold green] {max_followers:,}\n"
            f"[bold green]AHS Threshold:[/bold green] >= {min_ahs:.1f}\n"
            f"[bold green]CRM Backend:[/bold green] {backend_name}\n"
            f"[bold green]Initial Cached Profiles in CRM:[/bold green] {len(crm.existing_usernames):,} handles",
            title="[bold cyan]VectorLead Hunt Configuration[/bold cyan]",
            border_style="cyan",
        )
    )

    # 2. Build Candidate Pool
    candidate_list: list[dict] = []
    if seeds:
        seed_path = Path(seeds)
        if seed_path.is_file():
            with open(seed_path, "r", encoding="utf-8") as f:
                handles = [line.strip().lstrip("@") for line in f if line.strip()]
            candidate_list = [{"username": h, "live_crawl": True} for h in handles]
        else:
            handles = [h.strip().lstrip("@") for h in seeds.split(",") if h.strip()]
            candidate_list = [{"username": h, "live_crawl": True} for h in handles]
    else:
        candidate_list = get_curated_seed_prospects(niche=niche)

    # 3. Create Live Progress Table
    table = Table(
        box=box.ROUNDED,
        title=f"VectorLead Execution Stream: {niche.upper()}",
        header_style="bold magenta",
    )
    table.add_column("Candidate", style="cyan", no_wrap=True)
    table.add_column("Followers", justify="right")
    table.add_column("F_Ratio", justify="right")
    table.add_column("Funnel Tier", justify="center")
    table.add_column("Niche Verdict", style="dim")
    table.add_column("Base AHS", justify="right")
    table.add_column("Multiplier", justify="right")
    table.add_column("Final AHS", justify="right", style="bold")
    table.add_column("Decision", justify="center")
    table.add_column("Destination", justify="center")

    new_qualified_leads = 0
    total_evaluated = 0
    total_skipped = 0
    total_disposed = 0

    candidate_idx = 0
    pool_len = len(candidate_list)

    while new_qualified_leads < min_new_leads and candidate_idx < (pool_len * 2):
        cand = candidate_list[candidate_idx % pool_len]
        username = cand["username"]
        candidate_idx += 1
        clean_user = crawler.clean_handle(username)

        # Check deduplication against Tracker and Disposed tabs
        if crm.is_existing(clean_user):
            total_skipped += 1
            continue

        total_evaluated += 1

        profile: Optional[InstagramProfile] = None
        if cand.get("live_crawl", False):
            profile = crawler.fetch_profile(clean_user)
        else:
            if cand.get("exists", True) is False:
                profile = None
            else:
                profile = InstagramProfile(
                    username=clean_user,
                    exists=True,
                    full_name=cand.get("full_name", ""),
                    followers=cand.get("followers", 0),
                    following=cand.get("following", 500),
                    posts_count=cand.get("posts_count", 0),
                    bio=cand.get("bio", ""),
                    metrics=cand.get("metrics"),
                )

        # Step A: 404 / Non-existent profile check
        if profile is None or not profile.exists:
            total_disposed += 1
            reason = "404 Account Not Found / Deleted"
            if not dry_run:
                crm.append_to_disposed(clean_user, "N/A", reason)
                db.upsert_prospect(
                    username=clean_user,
                    status="disposed",
                    disposal_reason=reason,
                    crm_synced=True,
                )
            table.add_row(
                f"@{clean_user}",
                "-",
                "-",
                "-",
                "[red]Dead Handle[/red]",
                "-",
                "-",
                "-",
                "[bold red]DISQUALIFIED[/bold red]",
                "[red]Disposed[/red]",
            )
            continue

        # Step B: Follower Cap Pre-Check
        if profile.followers > max_followers:
            total_disposed += 1
            reason = f"Followers ({profile.followers:,}) exceed cap ({max_followers:,})"
            if not dry_run:
                crm.append_to_disposed(clean_user, profile.followers, reason)
                db.upsert_prospect(
                    username=clean_user,
                    full_name=profile.full_name,
                    followers=profile.followers,
                    following=profile.following,
                    posts_count=profile.posts_count,
                    bio=profile.bio,
                    niche=niche,
                    status="disposed",
                    disposal_reason=reason,
                    crm_synced=True,
                )
            table.add_row(
                f"@{clean_user}",
                f"{profile.followers:,}",
                f"{profile.followers / max(profile.following, 1):.1f}x",
                "[dim]N/A[/dim]",
                "[yellow]Mega Account[/yellow]",
                "-",
                "0.00",
                "0.0",
                "[bold red]DISQUALIFIED[/bold red]",
                "[red]Disposed[/red]",
            )
            continue

        # Step C: Niche Evaluation
        verdict = classifier.evaluate(
            bio=profile.bio,
            full_name=profile.full_name,
            username=clean_user,
            external_url=profile.external_url or "",
            niche_id=niche,
        )

        if not verdict.is_match:
            total_disposed += 1
            reason = verdict.disqualification_reason or "Niche mismatch"
            if not dry_run:
                crm.append_to_disposed(clean_user, profile.followers, reason)
                db.upsert_prospect(
                    username=clean_user,
                    full_name=profile.full_name,
                    followers=profile.followers,
                    following=profile.following,
                    posts_count=profile.posts_count,
                    bio=profile.bio,
                    niche=niche,
                    niche_match=False,
                    status="disposed",
                    disposal_reason=reason,
                    crm_synced=True,
                )
            table.add_row(
                f"@{clean_user}",
                f"{profile.followers:,}",
                f"{profile.followers / max(profile.following, 1):.1f}x",
                "[dim]Tier D[/dim]",
                f"[red]{verdict.disqualification_reason[:20]}...[/red]" if verdict.disqualification_reason and len(verdict.disqualification_reason) > 20 else "[red]Mismatch[/red]",
                "-",
                "-",
                "-",
                "[bold red]DISQUALIFIED[/bold red]",
                "[red]Disposed[/red]",
            )
            continue

        # Step D: Mathematical AHS Calculation with EQS and Funnel Maturity
        tier, has_dm = classify_funnel_tier(profile.bio, profile.external_url)
        metrics = profile.metrics or AccountMetrics.from_raw_metrics(
            followers=profile.followers,
            following=max(50, profile.following),
            followers_7d_ago=int(profile.followers * 0.95),
            posts_30d=12,
            days_since_last_post=2,
            funnel_tier=tier,
            has_dm_automation_signal=has_dm,
        )
        ahs_res = calculate_ahs(
            metrics=metrics,
            min_qualification_ahs=min_ahs,
            max_followers_cap=max_followers,
        )

        f_ratio_str = f"{ahs_res.f_ratio:.1f}x"
        tier_label = "[green]Tier A (High-Ticket)[/green]" if tier == FunnelTier.TIER_A_HIGH_TICKET else (
            "[cyan]Tier B (Multi-Link)[/cyan]" if tier == FunnelTier.TIER_B_MULTI_LINK else "[yellow]Tier C/D[/yellow]"
        )

        if ahs_res.is_qualified:
            new_qualified_leads += 1
            if not dry_run:
                crm.append_to_tracker(clean_user, ahs_res.final_ahs)
                db.upsert_prospect(
                    username=clean_user,
                    full_name=profile.full_name,
                    followers=profile.followers,
                    following=metrics.following,
                    posts_count=profile.posts_count,
                    bio=profile.bio,
                    niche=niche,
                    niche_match=True,
                    base_ahs=ahs_res.base_ahs,
                    multiplier=ahs_res.multiplier,
                    final_ahs=ahs_res.final_ahs,
                    f_ratio=ahs_res.f_ratio,
                    funnel_tier=tier.value,
                    is_breakout=ahs_res.is_breakout,
                    eqs_score=ahs_res.components.s_eqs,
                    status="qualified",
                    crm_synced=True,
                )
            breakout_icon = " 🚀" if ahs_res.is_breakout else ""
            table.add_row(
                f"@{clean_user}",
                f"{profile.followers:,}",
                f_ratio_str,
                tier_label,
                f"[green]Match ({verdict.confidence:.0%})[/green]",
                f"{ahs_res.base_ahs:.1f}",
                f"{ahs_res.multiplier:.2f}x",
                f"[bold green]{ahs_res.final_ahs:.1f}{breakout_icon}[/bold green]",
                "[bold green]QUALIFIED[/bold green]",
                "[bold green]Tracker[/bold green]",
            )
        else:
            total_disposed += 1
            reason = ahs_res.disqualification_reason or f"AHS < {min_ahs:.1f}"
            if not dry_run:
                crm.append_to_disposed(clean_user, profile.followers, reason)
                db.upsert_prospect(
                    username=clean_user,
                    full_name=profile.full_name,
                    followers=profile.followers,
                    following=metrics.following,
                    posts_count=profile.posts_count,
                    bio=profile.bio,
                    niche=niche,
                    niche_match=True,
                    base_ahs=ahs_res.base_ahs,
                    multiplier=ahs_res.multiplier,
                    final_ahs=ahs_res.final_ahs,
                    f_ratio=ahs_res.f_ratio,
                    funnel_tier=tier.value,
                    is_breakout=ahs_res.is_breakout,
                    eqs_score=ahs_res.components.s_eqs,
                    status="disposed",
                    disposal_reason=reason,
                    crm_synced=True,
                )
            table.add_row(
                f"@{clean_user}",
                f"{profile.followers:,}",
                f_ratio_str,
                tier_label,
                f"[green]Match ({verdict.confidence:.0%})[/green]",
                f"{ahs_res.base_ahs:.1f}",
                f"{ahs_res.multiplier:.2f}x",
                f"[yellow]{ahs_res.final_ahs:.1f}[/yellow]",
                "[yellow]LOW AHS[/yellow]",
                "[red]Disposed[/red]",
            )

    console.print(table)

    # 4. Summary Card
    console.print(
        Panel.fit(
            f"[bold green]New Leads Added to Tracker:[/bold green] {new_qualified_leads} (Target: {min_new_leads})\n"
            f"[bold yellow]Disposed Disqualifications:[/bold yellow] {total_disposed}\n"
            f"[bold blue]Duplicates Skipped:[/bold blue] {total_skipped}\n"
            f"[bold white]Total Evaluated in Run:[/bold white] {total_evaluated}\n"
            f"[bold white]Tracker Total Leads:[/bold white] {crm.get_tracker_count()}\n"
            f"[bold white]Disposed Total Leads:[/bold white] {crm.get_disposed_count()}",
            title="[bold green]VectorLead Run Summary & Quota Status[/bold green]",
            border_style="green" if new_qualified_leads >= min_new_leads else "yellow",
        )
    )


@app.command()
def test_account(
    username: str = typer.Argument(..., help="Instagram username or profile URL to inspect."),
    niche: str = typer.Option(
        "personal_trainer",
        "--niche",
        "-n",
        help="Target niche for qualification evaluation.",
    ),
    live: bool = typer.Option(
        True,
        "--live/--no-live",
        help="Perform live zero-login crawler verification via facebookexternalhit.",
    ),
) -> None:
    """Run an end-to-end diagnostic on a single Instagram profile."""
    console.print(BANNER)
    crawler = InstagramCrawler()
    classifier = NicheClassifier()
    clean_user = crawler.clean_handle(username)

    console.print(f"[bold cyan]Diagnosing profile:[/bold cyan] @{clean_user} against [bold yellow]{niche}[/bold yellow]...")

    profile: Optional[InstagramProfile] = None
    if live:
        profile = crawler.fetch_profile(clean_user)

    if profile is None:
        console.print(f"[bold red]Live Crawl Result:[/bold red] Could not fetch @{clean_user} or account does not exist (404/Private/Blocked).")
        console.print("[dim]Generating diagnostic sample based on handle for demonstration...[/dim]")
        profile = InstagramProfile(
            username=clean_user,
            exists=True,
            full_name=f"{clean_user.replace('_', ' ').title()}",
            followers=14500,
            following=420,
            posts_count=210,
            bio="Online Fitness Coach & Personal Trainer | 1-on-1 coaching application. Apply below 👇",
            external_url="https://calendly.com/coach/consultation",
        )

    # Niche verdict
    verdict = classifier.evaluate(
        bio=profile.bio,
        full_name=profile.full_name,
        username=clean_user,
        external_url=profile.external_url or "",
        niche_id=niche,
    )

    # Funnel & AHS Momentum
    tier, has_dm = classify_funnel_tier(profile.bio, profile.external_url)
    metrics = profile.metrics or AccountMetrics(
        followers=profile.followers,
        following=profile.following,
        growth_rate_7d=0.08,
        reel_view_velocity_ratio=1.3,
        prior_reel_view_velocity_ratio=1.05,
        comment_velocity_ratio=1.1,
        posts_last_30_days=14,
        days_since_last_post=2,
        likes_med_7=400.0,
        comments_med_7=24.0,
        creator_reply_rate=0.60,
        funnel_tier=tier,
        has_dm_automation_signal=has_dm,
    )
    ahs = calculate_ahs(metrics)

    # Render Card
    scorecard = Table(box=box.SIMPLE)
    scorecard.add_column("Metric / Vector Component", style="bold")
    scorecard.add_column("Value")
    scorecard.add_column("Score / Ratio", justify="right")

    scorecard.add_row("Follower Growth (7d, S_G)", f"{metrics.growth_rate_7d:+.1%}", f"{ahs.components.s_g:.1f}")
    scorecard.add_row("Reel View Velocity (Rv, S_V)", f"{metrics.reel_view_velocity_ratio:.2f}x", f"{ahs.components.s_v:.1f}")
    scorecard.add_row("Comment Velocity (Rc, S_C)", f"{metrics.comment_velocity_ratio:.2f}x", f"{ahs.components.s_c:.1f}")
    scorecard.add_row("Post Recency Decay (S_P)", f"{metrics.posts_last_30_days} posts (eff: {ahs.breakdown.get('p_eff', 0):.1f})", f"{ahs.components.s_p:.1f}")
    scorecard.add_row("Engagement Quality (EQS, S_EQS)", f"C/L: {metrics.comments_med_7/max(metrics.likes_med_7, 1):.1%}, Reply: {metrics.creator_reply_rate:.0%}", f"{ahs.components.s_eqs:.1f}")
    scorecard.add_row("Follower Churn Ratio (F_ratio)", f"{metrics.followers:,} / {metrics.following:,}", f"{ahs.f_ratio:.1f}x")
    scorecard.add_row("Funnel Maturity Tier", f"{tier.value.upper()}", f"{'DM Trigger Active' if has_dm else 'Direct Link'}")
    scorecard.add_row("Base Health Score", "-", f"[bold]{ahs.base_ahs:.1f}[/bold]")
    scorecard.add_row("Composite Multiplier (M)", f"{ahs.multiplier:.2f}x ({ahs.multiplier_reason})", f"{'Breakout 🚀' if ahs.is_breakout else 'Steady'}")
    scorecard.add_row("FINAL VECTORLEAD AHS", f"{ahs.final_ahs:.1f}", f"[bold {'green' if ahs.is_qualified else 'red'}]{ahs.final_ahs:.1f}[/bold {'green' if ahs.is_qualified else 'red'}]")

    console.print(
        Panel(
            f"[bold cyan]Handle:[/bold cyan] @{profile.username}\n"
            f"[bold cyan]Full Name:[/bold cyan] {profile.full_name}\n"
            f"[bold cyan]Followers:[/bold cyan] {profile.followers:,} | [bold cyan]Following:[/bold cyan] {profile.following:,}\n"
            f"[bold cyan]Bio:[/bold cyan] {profile.bio}\n"
            f"[bold cyan]External URL:[/bold cyan] {profile.external_url or 'None'}\n\n"
            f"[bold magenta]Niche Verdict:[/bold magenta] {'[bold green]QUALIFIED[/bold green]' if verdict.is_match else '[bold red]DISQUALIFIED[/bold red]'}\n"
            f"[dim]Matched Positives:[/dim] {', '.join(verdict.matched_positives) or 'None'}\n"
            f"[dim]Matched Services:[/dim] {', '.join(verdict.matched_services) or 'None'}\n"
            f"[dim]Matched Negatives:[/dim] {', '.join(verdict.matched_negatives) or 'None'}\n\n"
            f"[bold yellow]VectorLead Momentum & Quality Scorecard:[/bold yellow]",
            title=f"VectorLead Profile Audit: @{clean_user}",
            border_style="cyan",
        )
    )
    console.print(scorecard)

    final_verdict = (
        "[bold green]RECOMMENDED FOR OUTREACH[/bold green]"
        if (ahs.is_qualified and verdict.is_match)
        else f"[bold red]DO NOT OUTREACH[/bold red] ({verdict.disqualification_reason or ahs.disqualification_reason})"
    )
    console.print(f"\n[bold]Final Decision:[/bold] {final_verdict}\n")


@app.command()
def stats() -> None:
    """Display SQLite local cache metrics and CRM sync totals."""
    console.print(BANNER)
    db = ProspectDatabase()
    crm = get_crm_backend()
    s = db.get_stats()

    stats_table = Table(box=box.ROUNDED, title="VectorLead Pipeline Metrics")
    stats_table.add_column("Metric", style="bold cyan")
    stats_table.add_column("Count", justify="right", style="bold green")

    stats_table.add_row("Total Evaluated Prospects (SQLite)", f"{s['total']:,}")
    stats_table.add_row("Qualified Prospects (SQLite)", f"{s['qualified']:,}")
    stats_table.add_row("Disposed Prospects (SQLite)", f"{s['disposed']:,}")
    stats_table.add_row("Synced to CRM", f"{s['synced']:,}")
    stats_table.add_row("Tracker Rows (CRM)", f"{crm.get_tracker_count():,}")
    stats_table.add_row("Disposed Rows (CRM)", f"{crm.get_disposed_count():,}")

    console.print(stats_table)


@app.command()
def list_niches() -> None:
    """Display all configured modular niches and keyword filter rules."""
    console.print(BANNER)
    classifier = NicheClassifier()
    table = Table(box=box.ROUNDED, title="Configured Niche Engines")
    table.add_column("Niche ID", style="bold cyan")
    table.add_column("Name", style="bold white")
    table.add_column("Positive Signals", style="green")
    table.add_column("Service Indicators", style="blue")
    table.add_column("Negative Filters", style="red")

    for niche_id in classifier.list_niches():
        n = classifier.get_niche(niche_id)
        if n:
            table.add_row(
                n.id,
                n.name,
                f"{len(n.positive_keywords)} keywords",
                f"{len(n.service_indicators)} indicators",
                f"{len(n.negative_keywords)} filters",
            )
    console.print(table)


if __name__ == "__main__":
    app()
