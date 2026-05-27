# free_outbound_agent

An open-source AI-powered outbound agent for email and LinkedIn. Point it at your ICP, describe your product, and it finds prospects, writes genuinely personalized messages using an LLM, and delivers them — on a schedule you control.

No SaaS subscription. No per-seat pricing. Runs from your own machine or a server.

---

## What it does

```
1. Discover   →  scrapes GitHub, Dev.to, and Product Hunt for people matching your ICP
2. Compose    →  uses Claude or GPT-4 to write a personalized message per lead
3. Deliver    →  email: sends automatically via SMTP/Gmail/Zoho
                 LinkedIn: prints a copy-paste queue (you send manually — LinkedIn blocks bots)
4. Track      →  logs leads to HubSpot or Zoho CRM, marks sent to avoid duplicates
```

Every part is swappable. Don't use Zoho? Swap in Gmail. Don't want Claude? Use OpenAI. The config file controls everything — no code changes required for most setups.

---

## Quickstart

### 1. Clone and install

```bash
git clone https://github.com/Dumebii/free_outbound_agent.git
cd free_outbound_agent
pip install -r requirements.txt
```

### 2. Set up credentials

```bash
cp .env.example .env
```

Open `.env` and fill in the credentials for whichever providers you're using.

### 3. Configure your campaign

Edit `config.yaml` — at minimum set `company.name`, `company.description`, `company.from_email`, and your `compose.provider`.

### 4. Your first run

**Email pipeline:**
```bash
# 1. Discover leads and write them to leads.csv (no emails sent)
python pipeline.py --scrape-only

# 2. Review leads.csv before anything goes out

# 3. Preview what emails would look like — no API calls, completely free
python pipeline.py --dry-run

# 4. Send today's batch
python pipeline.py --send-only
```

**LinkedIn pipeline:**
```bash
# 1. Reuse the same leads.csv from above (or scrape first)

# 2. Preview connection notes before logging anything
python linkedin_pipeline.py --queue --dry-run

# 3. Run the interactive queue — copy-paste each note on LinkedIn, press Enter to log
python linkedin_pipeline.py --queue
```

---

## Project structure

```
free_outbound_agent/
├── pipeline.py              # Email pipeline orchestrator
├── linkedin_pipeline.py     # LinkedIn pipeline orchestrator
├── config.yaml              # Your ICP, tone, provider choices (both channels)
├── .env                     # API keys (never committed)
├── .env.example             # Template to copy from
├── requirements.txt
│
├── sources/                 # Lead discovery (shared by both pipelines)
│   ├── github.py            # GitHub user search by bio keywords + follower count
│   ├── devto.py             # Dev.to by tag, email resolved via GitHub
│   └── producthunt.py       # PH makers via GraphQL API, email resolved via GitHub
│
├── compose/
│   └── composer.py          # LLM prompt → Claude or OpenAI → email or LinkedIn message
│
├── send/                    # Email sending backends
│   ├── smtp.py              # Generic SMTP (Fastmail, Namecheap, Mailgun, SendGrid, etc.)
│   ├── gmail.py             # Gmail SMTP (app password)
│   └── zohomail.py          # Zoho Mail REST API
│
├── crm/                     # CRM sync (email pipeline only)
│   ├── hubspot.py
│   └── zohocrm.py
│
├── linkedin/                # LinkedIn-specific modules
│   ├── cap.py               # Daily cap tracker (20 requests/day)
│   └── store.py             # LinkedIn tracking CSV (separate from email sent.csv)
│
└── store/
    └── leads.py             # CSV-backed lead store + email sent tracking
```

---

## Email pipeline

### Basic usage

```bash
python pipeline.py                          # scrape new leads + send today's batch
python pipeline.py --scrape-only            # only discover leads, do not send
python pipeline.py --send-only              # only send, skip scrape
python pipeline.py --follow-up              # send sequence follow-ups to leads due for next step
python pipeline.py --dry-run                # preview emails without sending or API calls
python pipeline.py --mark-replied user@x.com  # mark replied — removes from sequence
```

### Configuration

#### `company`

| Field | Description |
|---|---|
| `name` | Your company name |
| `description` | What you do and who for — the LLM uses this to write relevant emails |
| `from_name` | Sender name that appears in the inbox |
| `from_email` | Must match the account configured in your email provider |

#### `compose`

| Field | Options | Description |
|---|---|---|
| `provider` | `claude`, `openai` | Which LLM to use |
| `model` | any valid model ID | e.g. `claude-opus-4-5`, `gpt-4o` |
| `tone` | free text | Describe the voice — "direct", "warm", "technical" |
| `banned_words` | list | Words the LLM will never use |

#### `icp.segments`

Define as many segments as you want. Each has a `name` and `keywords` matched against the lead's bio:

```yaml
icp:
  segments:
    - name: devrel
      keywords: [developer advocate, devrel, developer evangelist]
    - name: founder
      keywords: [founder, indie hacker, bootstrapped]
```

#### `sources.github`

| Field | Description |
|---|---|
| `enabled` | `true` / `false` |
| `token_env` | Env var name holding your GitHub PAT (default: `GITHUB_TOKEN`) |
| `min_followers` | Minimum follower count |
| `queries` | GitHub search queries (follower filter appended automatically) |

GitHub query examples:
```yaml
queries:
  - '"developer advocate" in:bio'
  - '"technical writer" in:bio'
  - '"founder" "building" in:bio'
  - '"indie hacker" in:bio'
```

#### `sources.devto`

| Field | Description |
|---|---|
| `enabled` | `true` / `false` |
| `tags` | Dev.to tags to search |
| `min_reactions` | Minimum reactions — filters for influential authors |

Dev.to email resolution requires leads to have a linked GitHub account.

#### `sources.producthunt`

| Field | Description |
|---|---|
| `enabled` | `true` / `false` |
| `token_env` | Env var name for your PH developer token (default: `PRODUCTHUNT_TOKEN`) |
| `topics` | PH topic slugs — see [producthunt.com/topics](https://producthunt.com/topics) |
| `min_votes` | Minimum upvotes for a product |
| `pages_per_topic` | Pages of 50 posts to scan per topic |

#### `send`

| Field | Options | Description |
|---|---|---|
| `provider` | `smtp`, `gmail`, `zohomail` | Email backend |
| `daily_limit` | integer | Max emails per run |
| `delay_seconds` | integer | Pause between sends |

**Recommended delay by volume:**

| Emails/day | Delay | Notes |
|---|---|---|
| ≤ 50 | 60s | Safe for most providers |
| 51–100 | 90s | Monitor for blocks |
| 100+ | 120s+ | Warm up the account first |

### Sequences (multi-step follow-ups)

Enable in `config.yaml`:

```yaml
sequences:
  enabled: true
  follow_up_slots: 10
  steps:
    - step: 1
      delay_days: 0
    - step: 2
      delay_days: 3
      subject_hint: "new angle worth sharing"
    - step: 3
      delay_days: 7
      subject_hint: "closing the loop"
```

```bash
python pipeline.py --send-only      # new outreach (step 1)
python pipeline.py --follow-up      # follow-ups (steps 2 and 3, when due)
python pipeline.py --mark-replied user@example.com
```

---

## LinkedIn pipeline

LinkedIn actively restricts automation — connection requests and DMs sent via bots will get your account flagged. This pipeline solves the hard part (writing personalized messages at volume) while keeping you in control of the actual sending.

**What it automates:** message generation, state tracking, daily cap enforcement, copy-paste queue.  
**What you do manually:** open LinkedIn, find the person, paste the note, click send. ~30 seconds per lead.

### Basic usage

```bash
python linkedin_pipeline.py --queue              # show today's connection request queue
python linkedin_pipeline.py --queue --dry-run    # preview without logging
python linkedin_pipeline.py --follow-up          # DMs for connected leads due for next step
python linkedin_pipeline.py --mark-connected user@x.com  # record accepted connection
python linkedin_pipeline.py --mark-replied   user@x.com  # remove from sequence
python linkedin_pipeline.py --stats
```

### Workflow

```
Day 0   python linkedin_pipeline.py --queue
        → Shows 20 leads with LinkedIn search URL + personalized connection note
        → You open LinkedIn, find the person, paste the note, press Enter

        When someone accepts:
        python linkedin_pipeline.py --mark-connected user@example.com

Day 3+  python linkedin_pipeline.py --follow-up
        → Shows DMs for connected leads, ready to copy-paste

Day 7+  python linkedin_pipeline.py --follow-up
        → Shows closing DMs for step-2 leads
```

### Configuration

Add this to `config.yaml` (already included as a template):

```yaml
linkedin:
  enabled: false            # flip to true when ready
  daily_limit: 20           # LinkedIn recommends <=20 requests/day
  note_max_chars: 300       # LinkedIn's hard limit for connection notes

  store:
    sent_file: linkedin_sent.csv
    tracker_file: linkedin_daily_tracker.json

  sequences:
    enabled: true
    steps:
      - step: 1
        delay_days: 0
      - step: 2
        delay_days: 3
      - step: 3
        delay_days: 7
```

LinkedIn uses the same `compose` and `icp` settings as email — same LLM provider, same segments, same banned words. The prompts are adapted for LinkedIn format automatically.

### State files

| File | Contents |
|---|---|
| `linkedin_sent.csv` | One row per lead: step, request date, connected date, replied state |
| `linkedin_daily_tracker.json` | Today's request count, resets at midnight |

Both are git-ignored. Delete `linkedin_sent.csv` to reset.

---

## Credentials setup

### LLM (required)

- **Claude:** API key at [console.anthropic.com](https://console.anthropic.com) → `ANTHROPIC_API_KEY` in `.env`
- **OpenAI:** API key at [platform.openai.com](https://platform.openai.com) → `OPENAI_API_KEY` in `.env`

### GitHub (required for lead discovery)

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Generate a classic token with `read:user` and `user:email` scopes
3. Add to `.env` as `GITHUB_TOKEN`

### Generic SMTP (recommended default for email)

```
SMTP_HOST=smtp.yourdomain.com
SMTP_PORT=465
SMTP_USER=you@yourdomain.com
SMTP_PASSWORD=your-password
```

Common providers:

| Provider | Host | Port |
|---|---|---|
| Fastmail | smtp.fastmail.com | 465 |
| Namecheap | mail.privateemail.com | 465 |
| Zoho Mail | smtp.zoho.com | 465 |
| SendGrid | smtp.sendgrid.net | 587 |
| Mailgun | smtp.mailgun.org | 587 |

### Gmail

1. Enable 2FA → [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → create app password
2. Add `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` to `.env`

### Zoho Mail

1. [api-console.zoho.com](https://api-console.zoho.com) → Self Client → generate code with scope `ZohoMail.messages.CREATE,ZohoMail.accounts.READ`
2. Exchange for refresh token, get account ID
3. Add `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, `ZOHO_MAIL_REFRESH_TOKEN`, `ZOHO_MAIL_ACCOUNT_ID`

### HubSpot CRM

1. HubSpot → Settings → Integrations → Private Apps → create app with `crm.objects.contacts.write`
2. Add `HUBSPOT_API_KEY` to `.env`. Free tier works.

### Zoho CRM

1. [api-console.zoho.com](https://api-console.zoho.com) → Self Client → scope `ZohoCRM.modules.ALL`
2. Add `ZOHO_CRM_REFRESH_TOKEN` (reuse same `ZOHO_CLIENT_ID` / `ZOHO_CLIENT_SECRET`)

### Product Hunt

1. [producthunt.com/v2/oauth/applications](https://www.producthunt.com/v2/oauth/applications) → create application → copy Developer Token
2. Add as `PRODUCTHUNT_TOKEN` to `.env`

---

## How messages are generated

The LLM receives your company description, the lead's name/bio/company/profile, your tone instructions, and your banned word list. It writes a message that opens with a specific observation about the person and connects their work to a real problem you solve.

**Email** returns a subject line + HTML body (max 120 words).  
**LinkedIn** returns plain text: connection notes are kept under 300 characters; follow-up DMs are 2–3 sentences.

Preview before sending:
```bash
python pipeline.py --dry-run
python linkedin_pipeline.py --queue --dry-run
```

---

## Running on a schedule

**Linux / macOS (cron):**
```bash
# Email: send every day at 9am
0 9 * * * cd /path/to/outbound-agent && python pipeline.py --send-only

# Scrape weekly, send daily
0 8 * * 1 cd /path/to/outbound-agent && python pipeline.py --scrape-only
0 9 * * * cd /path/to/outbound-agent && python pipeline.py --send-only
```

**Windows (Task Scheduler):**  
Create a Basic Task → Daily → Action: `python C:\path\to\free_outbound_agent\pipeline.py --send-only`

LinkedIn requires manual sends so no cron is needed — just run `--queue` once a day.

---

## Extending

### Add a new lead source

```python
# sources/myplatform.py
from .base import LeadSource

class MyPlatformSource(LeadSource):
    def scrape(self, seen_emails, seen_usernames):
        # return list of dicts: Name, Username, Email, Company, Bio, Website, Twitter, Followers, Source, Profile
        return leads
```

Register in `sources/__init__.py` and wire into `pipeline.py` / `linkedin_pipeline.py`.

### Add a new email sender

```python
# send/myservice.py
from .base import EmailSender

class MyServiceSender(EmailSender):
    def send(self, to_email, to_name, subject, html_body):
        return True  # or False on failure
```

Register in `send/__init__.py`'s `get_sender()` factory.

---

## Limitations

- **Dev.to email resolution** requires leads to have a linked GitHub account. Authors without GitHub won't be included.
- **GitHub search** returns at most 1,000 results per query. Use multiple targeted queries.
- **Product Hunt developer token** only exposes the primary maker per product. Use more topics and pages to build volume.
- **LinkedIn sending** is manual by design — automation risks account restrictions.
- **LLM costs** apply per message generated. At ~400 tokens/call, 50 emails/day costs ~$0.30–$1.50/day depending on model. LinkedIn notes are shorter (~100 tokens each).

---

## License

MIT — use it, modify it, build on it.
