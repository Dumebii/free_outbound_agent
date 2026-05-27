"""
linkedin_pipeline.py — LinkedIn outreach pipeline
===================================================
Usage:
  python linkedin_pipeline.py --queue              # show today's connection request queue
  python linkedin_pipeline.py --queue --dry-run    # preview without logging
  python linkedin_pipeline.py --follow-up          # DMs for connected leads due for next step
  python linkedin_pipeline.py --mark-connected user@x.com
  python linkedin_pipeline.py --mark-replied   user@x.com
  python linkedin_pipeline.py --stats

Workflow:
  Day 0  → --queue       (step 1: send connection requests — copy-paste queue)
           --mark-connected EMAIL  (when someone accepts)
  Day 3+ → --follow-up   (step 2: DM after connecting)
  Day 7+ → --follow-up   (step 3: closing DM)

LinkedIn's recommended limit is 20 connection requests/day. This pipeline
enforces that cap automatically.
"""

import sys
import argparse
from urllib.parse import quote_plus

import yaml
from dotenv import load_dotenv

from sources import GitHubSource, DevToSource, ProductHuntSource
from store   import LeadStore
from compose import generate_linkedin_message
from linkedin import LinkedInCap, LinkedInStore

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ── Config ─────────────────────────────────────────────────────────────────

def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify(lead: dict, config: dict) -> str:
    bio      = (lead.get("Bio") or "").lower()
    segments = config.get("icp", {}).get("segments", [])
    for seg in segments:
        for kw in seg.get("keywords", []):
            if kw.lower() in bio:
                return seg["name"]
    return segments[0]["name"] if segments else "general"


def make_linkedin_url(lead: dict) -> str:
    query = f"{lead.get('Name', '')} {lead.get('Company', '')}".strip()
    return f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(query)}"


def _wrap(text: str, width: int = 54) -> list[str]:
    words, line, lines = text.split(), "", []
    for word in words:
        candidate = f"{line} {word}".strip()
        if len(candidate) > width:
            if line:
                lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def _print_message_box(message: str, label: str = "MESSAGE"):
    print(f"\n  {label}:")
    print(f"  ┌{'─'*56}")
    for line in _wrap(message):
        print(f"  │ {line}")
    print(f"  └{'─'*56}")


# ── Scrape ──────────────────────────────────────────────────────────────────

def run_scrape(config: dict, store: LeadStore):
    seen_emails    = store.seen_emails()
    seen_usernames = store.seen_usernames()
    new_leads      = []

    src = config.get("sources", {})

    if src.get("github", {}).get("enabled", False):
        print("\n=== GitHub ===")
        found = GitHubSource(config).scrape(seen_emails, seen_usernames)
        new_leads.extend(found)
        print(f"[github] +{len(found)} new leads")

    if src.get("devto", {}).get("enabled", False):
        print("\n=== Dev.to ===")
        found = DevToSource(config).scrape(seen_emails, seen_usernames)
        new_leads.extend(found)
        print(f"[devto] +{len(found)} new leads")

    if src.get("producthunt", {}).get("enabled", False):
        print("\n=== Product Hunt ===")
        found = ProductHuntSource(config).scrape(seen_emails, seen_usernames)
        new_leads.extend(found)
        print(f"[producthunt] +{len(found)} new leads")

    store.append_leads(new_leads)
    print(f"\nTotal new leads discovered: {len(new_leads)}")


# ── Queue (step 1) ──────────────────────────────────────────────────────────

def run_queue(config: dict, store: LeadStore, li_store: LinkedInStore,
              cap: LinkedInCap, dry_run: bool = False):
    available = cap.remaining()
    if available == 0:
        print(f"Daily cap reached. {cap.status()}")
        return

    all_leads  = store.load_leads()
    contacted  = li_store.contacted_emails()
    queue      = [l for l in all_leads if l.get("Email", "").lower() not in contacted]
    queue      = queue[:available]

    if not queue:
        print("No new leads available. Run --scrape or check leads.csv.")
        return

    li_cfg     = config.get("linkedin", {})
    note_max   = li_cfg.get("note_max_chars", 300)

    print(f"\n{'='*62}")
    print(f"  LinkedIn Queue  |  {cap.status()}")
    print(f"  {len(queue)} leads to contact today")
    print(f"{'='*62}")

    sent = 0
    for i, lead in enumerate(queue, 1):
        segment      = classify(lead, config)
        linkedin_url = make_linkedin_url(lead)

        if dry_run:
            note = "[DRY RUN — Claude not called]"
        else:
            try:
                note = generate_linkedin_message(lead, config, step=1)
                if len(note) > note_max:
                    note = note[:note_max]
            except Exception as e:
                print(f"  Compose error: {e} — skipping")
                continue

        char_count = len(note)
        print(f"\n{'─'*62}")
        print(f"[{i}/{len(queue)}]  {lead.get('Name', '?')}  |  {segment}")
        print(f"  Company : {lead.get('Company') or lead.get('Username') or '—'}")
        bio = (lead.get("Bio") or "")[:90]
        if bio:
            print(f"  Bio     : {bio}{'...' if len(lead.get('Bio','')) > 90 else ''}")
        print(f"\n  LinkedIn: {linkedin_url}")
        _print_message_box(note, label=f"CONNECTION NOTE ({char_count}/{note_max} chars)")

        if dry_run:
            print("\n  [DRY RUN — not logging]")
            continue

        print("\n  [Enter] mark sent  |  [s] skip  |  [q] quit")
        try:
            choice = input("  > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            break

        if choice == "q":
            print("Quit.")
            break
        elif choice == "s":
            print("  Skipped.")
        else:
            li_store.log_request(lead, segment, linkedin_url)
            cap.increment()
            sent += 1
            print(f"  Logged. ({cap.status()})")

    print(f"\n{'='*62}")
    print(f"  Session: {sent} connection request(s) logged.")
    print(f"  {cap.status()}")
    if sent:
        print(f"  Mark accepted connections: python linkedin_pipeline.py --mark-connected EMAIL")
        print(f"  Run follow-ups in 3+ days: python linkedin_pipeline.py --follow-up")
    print(f"{'='*62}\n")


# ── Follow-up (steps 2 & 3) ─────────────────────────────────────────────────

def run_followup(config: dict, li_store: LinkedInStore, cap: LinkedInCap, dry_run: bool = False):
    li_cfg  = config.get("linkedin", {})
    seq_cfg = li_cfg.get("sequences", {})

    if not seq_cfg.get("enabled", True):
        print("LinkedIn sequences disabled. Set linkedin.sequences.enabled: true in config.yaml")
        return

    available = cap.remaining()
    if available == 0:
        print(f"Daily cap reached. {cap.status()}")
        return

    steps = [s for s in seq_cfg.get("steps", []) if s.get("step", 1) > 1]
    if not steps:
        steps = [{"step": 2, "delay_days": 3}, {"step": 3, "delay_days": 7}]

    sent = 0
    for step_cfg in steps:
        step       = step_cfg["step"]
        delay_days = step_cfg.get("delay_days", 3 if step == 2 else 7)
        due        = li_store.get_followup_due(step=step, delay_days=delay_days)
        remaining  = available - sent

        if not due:
            label = "step 2 (need --mark-connected first)" if step == 2 else "step 3"
            print(f"No leads due for {label}.")
            continue

        batch = due[:remaining]
        print(f"\n{'='*62}")
        print(f"  Step {step} Follow-Ups  |  {len(batch)} leads ready  |  {cap.status()}")
        print(f"{'='*62}")

        for i, row in enumerate(batch, 1):
            lead = {"Name": row["name"], "Bio": "", "Company": "", "Email": row["email"]}

            if dry_run:
                message = "[DRY RUN — Claude not called]"
            else:
                try:
                    message = generate_linkedin_message(lead, config, step=step)
                except Exception as e:
                    print(f"  Compose error: {e} — skipping")
                    continue

            print(f"\n{'─'*62}")
            print(f"[{i}/{len(batch)}]  {row['name']}  |  {row.get('segment', '—')}")
            print(f"  LinkedIn: {row.get('linkedin_search_url', '—')}")
            _print_message_box(message, label=f"STEP {step} MESSAGE")

            if dry_run:
                print("\n  [DRY RUN — not logging]")
                continue

            print("\n  [Enter] mark sent  |  [s] skip  |  [q] quit")
            try:
                choice = input("  > ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                return

            if choice == "q":
                return
            elif choice == "s":
                print("  Skipped.")
            else:
                li_store.advance_step(row["email"], step)
                cap.increment()
                sent += 1
                print(f"  Logged. ({cap.status()})")

        if sent >= available:
            print("\nDaily cap reached.")
            break

    print(f"\n  Session: {sent} follow-up(s) sent.\n")


# ── Stats ───────────────────────────────────────────────────────────────────

def run_stats(li_store: LinkedInStore, cap: LinkedInCap):
    s     = li_store.stats()
    total = s["total"]
    rate  = f"{s['connected']/total*100:.0f}%" if total else "—"

    print(f"\n{'='*50}")
    print(f"  LinkedIn Pipeline Stats")
    print(f"{'='*50}")
    print(f"  Requests sent     : {total}")
    print(f"  Connections       : {s['connected']}  ({rate} accept rate)")
    print(f"  Follow-up sent    : {s['step2']}")
    print(f"  Closing sent      : {s['step3']}")
    print(f"  Replied           : {s['replied']}")
    print(f"  {cap.status()}")
    print(f"{'='*50}\n")


# ── Entry point ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LinkedIn outreach pipeline")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--queue",          action="store_true", help="Show today's connection request queue")
    group.add_argument("--follow-up",      action="store_true", help="Show follow-up DMs for connected leads")
    group.add_argument("--mark-connected", metavar="EMAIL",     help="Record that EMAIL accepted the connection")
    group.add_argument("--mark-replied",   metavar="EMAIL",     help="Remove EMAIL from sequence (they replied)")
    group.add_argument("--stats",          action="store_true", help="Show pipeline summary")
    parser.add_argument("--dry-run",       action="store_true", help="Preview without logging")
    parser.add_argument("--config",        default="config.yaml")
    args = parser.parse_args()

    config   = load_config(args.config)
    li_cfg   = config.get("linkedin", {})
    store_cfg = li_cfg.get("store", {})

    lead_store_cfg = config.get("store", {})
    store    = LeadStore(
        leads_file=lead_store_cfg.get("leads_file", "leads.csv"),
        sent_file =lead_store_cfg.get("sent_file",  "sent.csv"),
    )
    li_store = LinkedInStore(sent_file=store_cfg.get("sent_file", "linkedin_sent.csv"))
    cap      = LinkedInCap(
        tracker_file=store_cfg.get("tracker_file", "linkedin_daily_tracker.json"),
        daily_limit =li_cfg.get("daily_limit", 20),
    )

    if args.queue:
        run_queue(config, store, li_store, cap, dry_run=args.dry_run)
    elif args.follow_up:
        run_followup(config, li_store, cap, dry_run=args.dry_run)
    elif args.mark_connected:
        li_store.mark_connected(args.mark_connected)
    elif args.mark_replied:
        li_store.mark_replied(args.mark_replied)
    elif args.stats:
        run_stats(li_store, cap)


if __name__ == "__main__":
    main()
