# outbound-agent

An open-source AI-powered outbound email agent. Point it at your ICP, describe your product, and it finds prospects, writes genuinely personalized emails using an LLM, syncs them to your CRM, and sends — on a schedule you control.

No SaaS subscription. No per-seat pricing. Runs from your own machine or a server.

---

## What it does

```
1. Discover   →  scrapes GitHub and Dev.to for people matching your ICP
2. Compose    →  uses Claude or GPT-4 to write a personalized email per lead
3. Send       →  delivers via Zoho Mail REST API or Gmail SMTP
4. Track      →  logs leads to Zoho CRM, marks sent to avoid duplicates
```

Every part is swappable. Don't use Zoho? Swap in Gmail. Don't want Claude? Use OpenAI. The config file controls everything — no code changes required for most setups.

---

## Quickstart

### 1. Clone and install

```bash
git clone https://github.com/your-username/outbound-agent.git
cd outbound-agent
pip install -r requirements.txt
```

### 2. Set up credentials

```bash
cp .env.example .env
```

Open `.env` and fill in the credentials for whichever providers you're using. You only need the ones that match your `config.yaml` choices.

### 3. Configure your campaign

Edit `config.yaml`:

```yaml
company:
  name: "Your Company"
  description: |
    We help [ICP] do [outcome] by [mechanism].
    One paragraph is enough — the LLM uses this to write emails.
  from_name: "Your Name"
  from_email: "you@yourcompany.com"

compose:
  provider: claude        # or openai
  model: claude-opus-4-5

send:
  provider: zohomail      # or gmail
  daily_limit: 50         # emails per run
  delay_seconds: 60       # pause between sends
```

### 4. Run

```bash
# Full pipeline: scrape new leads, then send today's batch
python pipeline.py

# Just discover leads (no emails sent)
python pipeline.py --scrape-only

# Just send to existing leads (skip scraping)
python pipeline.py --send-only

# Preview emails without sending anything
python pipeline.py --dry-run
```

---

## Project structure

```
outbound-agent/
├── pipeline.py          # Main orchestrator — run this
├── config.yaml          # Your ICP, tone, provider choices
├── .env                 # API keys (never committed)
├── .env.example         # Template to copy from
├── requirements.txt
│
├── sources/             # Lead discovery
│   ├── github.py        # Searches GitHub by bio keywords
│   └── devto.py         # Scrapes Dev.to by tag, resolves emails via GitHub
│
├── compose/
│   └── composer.py      # LLM prompt + Claude/OpenAI call → subject + body
│
├── send/
│   ├── zohomail.py      # Zoho Mail REST API
│   └── gmail.py         # Gmail SMTP
│
├── crm/
│   └── zohocrm.py       # Zoho CRM lead upsert
│
└── store/
    └── leads.py         # CSV-backed lead store + sent tracking
```

---

## Configuration reference

### `company`

| Field | Description |
|---|---|
| `name` | Your company name — used in the LLM prompt |
| `description` | What you do and who for — the LLM uses this to write relevant emails |
| `from_name` | Sender name that appears in the inbox |
| `from_email` | Must match the account configured in your email provider |

### `compose`

| Field | Options | Description |
|---|---|---|
| `provider` | `claude`, `openai` | Which LLM to use |
| `model` | any valid model ID | e.g. `claude-opus-4-5`, `gpt-4o` |
| `tone` | free text | Describe the voice you want — "direct", "warm", "technical" |
| `banned_words` | list of strings | Words the LLM will never use in generated copy |

### `icp.segments`

Define as many segments as you want. Each has a `name` and a list of `keywords` matched against the lead's bio.

```yaml
icp:
  segments:
    - name: devrel
      keywords: [developer advocate, devrel, developer evangelist]
    - name: founder
      keywords: [founder, indie hacker, bootstrapped]
```

The LLM receives the matched segment name as context, helping it write more relevant copy.

### `sources.github`

| Field | Description |
|---|---|
| `enabled` | `true` / `false` |
| `token_env` | Name of the env var holding your GitHub PAT (default: `GITHUB_TOKEN`) |
| `min_followers` | Minimum follower count — filters out low-signal accounts |
| `queries` | List of GitHub search queries (follower filter is appended automatically) |

GitHub search query examples:
```yaml
queries:
  - '"developer advocate" in:bio'
  - '"technical writer" in:bio'
  - '"newsletter" "developer" in:bio'
  - '"indie hacker" in:bio'
  - '"founder" "building" in:bio'
```

Email extraction: tries the public profile email first, falls back to commit history.

### `sources.devto`

| Field | Description |
|---|---|
| `enabled` | `true` / `false` |
| `tags` | Dev.to tags to search (e.g. `devrel`, `newsletter`, `indiehacker`) |
| `min_reactions` | Minimum public reactions on articles — filters for influential authors |

Dev.to doesn't expose email addresses directly. The agent resolves them through linked GitHub accounts.

### `send`

| Field | Options | Description |
|---|---|---|
| `provider` | `zohomail`, `gmail` | Email sending backend |
| `daily_limit` | integer | Max emails per run — stays under provider limits |
| `delay_seconds` | integer | Pause between sends — lower values increase spam risk |

**Recommended delay by volume:**

| Emails/day | Delay | Notes |
|---|---|---|
| ≤ 50 | 60s | Safe for most providers |
| 51–100 | 90s | Monitor for blocks |
| 100+ | 120s+ | Warm up the account first |

### `crm`

| Field | Options | Description |
|---|---|---|
| `enabled` | `true` / `false` | Toggle CRM sync on/off |
| `provider` | `zohocrm`, `none` | CRM backend |

---

## Credentials setup

### GitHub (required for lead discovery)

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Generate a classic token with `read:user` and `user:email` scopes
3. Add to `.env` as `GITHUB_TOKEN`

### Zoho Mail (if `send.provider: zohomail`)

1. Go to [api-console.zoho.com](https://api-console.zoho.com) → **Self Client**
2. Generate a code with scope: `ZohoMail.messages.CREATE,ZohoMail.accounts.READ`
3. Exchange it for a refresh token:

```bash
curl -X POST "https://accounts.zoho.com/oauth/v2/token" \
  -d "grant_type=authorization_code" \
  -d "client_id=YOUR_CLIENT_ID" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "code=YOUR_GRANT_CODE"
```

4. Get your account ID:

```bash
curl "https://mail.zoho.com/api/accounts" \
  -H "Authorization: Zoho-oauthtoken YOUR_ACCESS_TOKEN"
```

5. Add `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, `ZOHO_MAIL_REFRESH_TOKEN`, `ZOHO_MAIL_ACCOUNT_ID` to `.env`

### Gmail (if `send.provider: gmail`)

1. Enable 2FA on your Google account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create an app password for "Mail"
4. Add `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` to `.env`

### LLM

- **Claude:** Get an API key at [console.anthropic.com](https://console.anthropic.com) → add as `ANTHROPIC_API_KEY`
- **OpenAI:** Get an API key at [platform.openai.com](https://platform.openai.com) → add as `OPENAI_API_KEY`

### Zoho CRM (optional)

1. Go to [api-console.zoho.com](https://api-console.zoho.com) → **Self Client**
2. Generate a code with scope: `ZohoCRM.modules.ALL`
3. Exchange for a refresh token (same curl as above)
4. Add `ZOHO_CRM_REFRESH_TOKEN` to `.env` (reuse the same `ZOHO_CLIENT_ID` / `ZOHO_CLIENT_SECRET`)

---

## How emails are generated

The LLM receives:
- Your company description
- The lead's name, bio, company, and profile URL
- Your tone instructions
- Your banned word list
- A list of links to choose from

It returns a subject line and HTML body. The prompt enforces a 120-word limit, no bullet points, no generic openers, and strict avoidance of your banned words — so the output reads like a human wrote it.

You can inspect what the LLM would send before committing:

```bash
python pipeline.py --dry-run
```

---

## Deduplication and sent tracking

- `leads.csv` — every discovered lead. New leads are appended; existing emails are skipped.
- `sent.csv` — every sent email. The pipeline skips anyone already in this file.

Both files are git-ignored. Delete `sent.csv` to reset (e.g. to run a follow-up sequence).

---

## Running on a schedule

**Linux / macOS (cron):**
```bash
# Send every day at 9am
0 9 * * * cd /path/to/outbound-agent && python pipeline.py --send-only
```

**Windows (Task Scheduler):**  
Create a Basic Task → Daily → Action: `python C:\path\to\outbound-agent\pipeline.py --send-only`

**Scrape weekly, send daily:**
```bash
# Scrape every Monday at 8am
0 8 * * 1 cd /path/to/outbound-agent && python pipeline.py --scrape-only

# Send every day at 9am
0 9 * * * cd /path/to/outbound-agent && python pipeline.py --send-only
```

---

## Extending

### Add a new lead source

```python
# sources/myplatform.py
from .base import LeadSource

class MyPlatformSource(LeadSource):
    def scrape(self, seen_emails, seen_usernames):
        # fetch leads from your platform
        # return list of dicts with keys:
        # Name, Username, Email, Company, Bio, Website, Twitter, Followers, Source, Profile
        return leads
```

Register it in `sources/__init__.py` and wire it into `pipeline.py`.

### Add a new email sender

```python
# send/myservice.py
from .base import EmailSender

class MyServiceSender(EmailSender):
    def send(self, to_email, to_name, subject, html_body):
        # call your service's API
        return True  # or False on failure
```

Register it in `send/__init__.py`'s `get_sender()` factory.

---

## Limitations

- **Dev.to email resolution** requires leads to have a linked GitHub account with a public email or commit history. Authors without GitHub won't be included.
- **GitHub search** returns at most 1,000 results per query. Use multiple targeted queries rather than broad ones.
- **Sending limits** depend entirely on your email provider. Start conservative (50/day, 60s delay) and increase only after the account is warmed up.
- **LLM costs** apply per email generated. At ~400 tokens per call, 50 emails/day costs roughly $0.30–$1.50/day depending on model.

---

## License

MIT — use it, modify it, build on it.
