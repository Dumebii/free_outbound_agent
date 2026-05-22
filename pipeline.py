"""
Outbound Agent — pipeline.py
============================
Usage:
  python pipeline.py                 # scrape new leads + send today's batch
  python pipeline.py --scrape-only   # only discover leads, do not send
  python pipeline.py --send-only     # only send to existing leads, skip scrape
  python pipeline.py --dry-run       # preview emails without sending
"""

import sys
import time
import argparse
import yaml
from dotenv import load_dotenv

from sources import GitHubSource, DevToSource
from compose import generate_email
from send    import get_sender
from crm     import get_crm
from store   import LeadStore

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ── Config ────────────────────────────────────────────────────────────────

def load_config(path="config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Scrape phase ──────────────────────────────────────────────────────────

def run_scrape(config: dict, store: LeadStore) -> int:
    seen_emails    = store.seen_emails()
    seen_usernames = store.seen_usernames()
    new_leads      = []

    sources_cfg = config.get("sources", {})

    if sources_cfg.get("github", {}).get("enabled", False):
        print("\n=== GitHub ===")
        github = GitHubSource(config)
        found  = github.scrape(seen_emails, seen_usernames)
        new_leads.extend(found)
        print(f"[github] +{len(found)} new leads")

    if sources_cfg.get("devto", {}).get("enabled", False):
        print("\n=== Dev.to ===")
        devto = DevToSource(config)
        found = devto.scrape(seen_emails, seen_usernames)
        new_leads.extend(found)
        print(f"[devto] +{len(found)} new leads")

    store.append_leads(new_leads)
    print(f"\nTotal new leads discovered: {len(new_leads)}")
    return len(new_leads)


# ── Send phase ────────────────────────────────────────────────────────────

def run_send(config: dict, store: LeadStore, dry_run: bool = False) -> dict:
    send_cfg     = config.get("send", {})
    daily_limit  = send_cfg.get("daily_limit", 50)
    delay        = send_cfg.get("delay_seconds", 60)

    all_leads  = store.load_leads()
    sent_today = store.load_sent()
    unsent     = [l for l in all_leads if l.get("Email", "").lower() not in sent_today]

    batch  = unsent[:daily_limit]
    total  = len(all_leads)
    sender = None if dry_run else get_sender(config)
    crm    = None if dry_run else get_crm(config)

    print(f"\n{total} total leads | {len(sent_today)} already sent | {len(unsent)} remaining")
    print(f"Sending batch of {len(batch)} ({'DRY RUN' if dry_run else f'{delay}s delay'})\n")

    results = {"sent": 0, "failed": 0, "skipped": 0}

    for i, lead in enumerate(batch, 1):
        name  = lead.get("Name", "")
        email = lead.get("Email", "")
        print(f"[{i}/{len(batch)}] {name} <{email}>")

        if dry_run:
            # Show what the LLM prompt looks like without making an API call
            from compose.composer import _build_prompt
            prompt = _build_prompt(lead, config)
            print(f"  [DRY RUN] Prompt preview:\n{prompt[:400]}...")
            print(f"  [DRY RUN] (no API call made)")
            results["skipped"] += 1
            continue

        # Generate email
        try:
            subject, html_body = generate_email(lead, config)
        except Exception as e:
            print(f"  COMPOSE ERROR — {e}")
            results["failed"] += 1
            continue

        # CRM sync (best-effort)
        if crm:
            lead_id = crm.upsert_lead(lead)
            print(f"  CRM: {lead_id or 'skipped'}")

        # Send
        ok = sender.send(email, name, subject, html_body)
        if ok:
            store.mark_sent(lead)
            print(f"  SENT")
            results["sent"] += 1
        else:
            print(f"  FAILED")
            results["failed"] += 1

        if i < len(batch):
            time.sleep(delay)

    return results


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Outbound Agent")
    parser.add_argument("--scrape-only", action="store_true", help="Only discover leads")
    parser.add_argument("--send-only",   action="store_true", help="Only send emails")
    parser.add_argument("--dry-run",     action="store_true", help="Preview without sending")
    parser.add_argument("--config",      default="config.yaml", help="Config file path")
    args = parser.parse_args()

    config = load_config(args.config)
    store  = LeadStore(
        leads_file=config.get("store", {}).get("leads_file", "leads.csv"),
        sent_file=config.get("store", {}).get("sent_file",  "sent.csv"),
    )

    if not args.send_only:
        run_scrape(config, store)

    if not args.scrape_only:
        results = run_send(config, store, dry_run=args.dry_run)
        print(f"\n--- Done ---")
        print(f"Sent:   {results['sent']}")
        print(f"Failed: {results['failed']}")
        if args.dry_run:
            print(f"Previewed: {results['skipped']}")


if __name__ == "__main__":
    main()
