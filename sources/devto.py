import os
import time
import requests
from .base import LeadSource


class DevToSource(LeadSource):
    """Scrapes Dev.to for leads by tag, then resolves emails via GitHub."""

    DEVTO_API = "https://dev.to/api"

    def __init__(self, config: dict):
        cfg = config.get("sources", {}).get("devto", {})
        self.tags = cfg.get("tags", [])
        self.min_reactions = cfg.get("min_reactions", 20)

        gh_cfg = config.get("sources", {}).get("github", {})
        token = os.getenv(gh_cfg.get("token_env", "GITHUB_TOKEN"), "")
        self.gh_headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    # ── Internal helpers ──────────────────────────────────────────────────

    def _devto_get(self, url, params=None, retries=4):
        for attempt in range(retries):
            try:
                resp = requests.get(url, params=params, timeout=20)
                if resp.status_code == 429:
                    print("  [devto] rate limited — waiting 30s...")
                    time.sleep(30)
                    continue
                return resp
            except Exception as e:
                wait = 2 ** attempt * 3
                print(f"  [devto] network error ({e.__class__.__name__}) — retrying in {wait}s...")
                time.sleep(wait)
        return None

    def _gh_get(self, url, params=None, retries=4):
        for attempt in range(retries):
            try:
                resp = requests.get(url, headers=self.gh_headers, params=params, timeout=20)
                remaining = int(resp.headers.get("X-RateLimit-Remaining", 1))
                if remaining < 5:
                    reset_at = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
                    wait = max(reset_at - time.time() + 2, 5)
                    print(f"  [github] rate limit — waiting {wait:.0f}s...")
                    time.sleep(wait)
                return resp
            except Exception as e:
                wait = 2 ** attempt * 3
                print(f"  [github] network error ({e.__class__.__name__}) — retrying in {wait}s...")
                time.sleep(wait)
        return None

    def _get_articles_by_tag(self, tag, pages=3):
        authors = {}
        for page in range(1, pages + 1):
            resp = self._devto_get(f"{self.DEVTO_API}/articles", params={
                "tag": tag, "per_page": 100, "page": page, "top": 365,
            })
            if not resp or resp.status_code != 200:
                break
            for a in resp.json():
                if a.get("public_reactions_count", 0) < self.min_reactions:
                    continue
                user = a.get("user", {})
                uname = user.get("username")
                if uname and uname not in authors:
                    authors[uname] = user.get("name") or uname
            time.sleep(1)
        return authors

    def _get_devto_profile(self, username):
        resp = self._devto_get(f"{self.DEVTO_API}/users/by_username", params={"url": username})
        return resp.json() if resp and resp.status_code == 200 else None

    def _get_github_email(self, github_username):
        """Try profile email then commit history."""
        resp = self._gh_get(f"https://api.github.com/users/{github_username}")
        gh_profile = None
        if resp and resp.status_code == 200:
            gh_profile = resp.json()
            email = gh_profile.get("email", "")
            if self.is_valid_email(email):
                return email, gh_profile

        repos = self._gh_get(
            f"https://api.github.com/users/{github_username}/repos",
            params={"sort": "pushed", "per_page": 10, "type": "owner"},
        )
        if not repos or repos.status_code != 200:
            return None, gh_profile

        for repo in repos.json():
            if repo.get("fork") or repo.get("private"):
                continue
            commits = self._gh_get(
                f"https://api.github.com/repos/{github_username}/{repo['name']}/commits",
                params={"author": github_username, "per_page": 1},
            )
            if not commits or commits.status_code != 200:
                continue
            data = commits.json()
            if not data:
                continue
            email = data[0].get("commit", {}).get("author", {}).get("email", "")
            if self.is_valid_email(email):
                return email, gh_profile
            time.sleep(0.5)

        return None, gh_profile

    # ── Public interface ──────────────────────────────────────────────────

    def scrape(self, seen_emails: set, seen_usernames: set) -> list[dict]:
        leads = []

        for tag in self.tags:
            print(f"\n[devto] Tag: #{tag}")
            authors = self._get_articles_by_tag(tag)
            print(f"[devto] Found {len(authors)} qualifying authors")

            for username, name in authors.items():
                key = f"devto:{username.lower()}"
                if key in seen_usernames:
                    continue
                seen_usernames.add(key)

                profile = self._get_devto_profile(username)
                if not profile:
                    continue

                bio       = (profile.get("summary") or "").strip().replace("\n", " ")
                website   = profile.get("website_url") or ""
                twitter   = profile.get("twitter_username") or ""
                github_u  = profile.get("github_username") or ""
                followers = profile.get("followers_count", 0)
                company   = (profile.get("organization") or "").strip()
                email, gh_profile = None, None

                if github_u:
                    if github_u.lower() in seen_usernames:
                        print(f"  DUPE {username} — GitHub user already in leads")
                        continue
                    email, gh_profile = self._get_github_email(github_u)
                    if email:
                        seen_usernames.add(github_u.lower())
                        if gh_profile:
                            bio       = bio or (gh_profile.get("bio") or "").strip().replace("\n", " ")
                            website   = website or gh_profile.get("blog") or ""
                            twitter   = twitter or gh_profile.get("twitter_username") or ""
                            followers = max(followers, gh_profile.get("followers", 0))

                if not self.is_valid_email(email):
                    print(f"  SKIP {username} — no email")
                    continue
                if email.lower() in seen_emails:
                    print(f"  DUPE {username} — duplicate email")
                    continue

                seen_emails.add(email.lower())
                leads.append({
                    "Name":      profile.get("name") or name,
                    "Username":  username,
                    "Email":     email,
                    "Company":   company,
                    "Bio":       bio[:200],
                    "Website":   website,
                    "Twitter":   twitter,
                    "Followers": followers,
                    "Source":    "devto",
                    "Profile":   f"https://dev.to/{username}",
                })
                print(f"  FOUND {name} <{email}> (devto) ({followers} followers)")
                time.sleep(0.5)

        return leads
