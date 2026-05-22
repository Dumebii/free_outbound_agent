import os
import time
import requests
from .base import LeadSource


class GitHubSource(LeadSource):
    """Scrapes GitHub for leads matching ICP search queries."""

    def __init__(self, config: dict):
        cfg = config.get("sources", {}).get("github", {})
        token = os.getenv(cfg.get("token_env", "GITHUB_TOKEN"), "")
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.min_followers = cfg.get("min_followers", 100)
        raw_queries = cfg.get("queries", [])
        # Append follower filter if not already in query
        self.queries = [
            q if "followers:" in q else f"{q} followers:>{self.min_followers}"
            for q in raw_queries
        ]

    # ── Internal helpers ──────────────────────────────────────────────────

    def _gh_get(self, url, params=None, retries=5):
        for attempt in range(retries):
            try:
                resp = requests.get(url, headers=self.headers, params=params, timeout=20)
                self._wait_for_rate_limit(resp.headers)
                return resp
            except Exception as e:
                wait = 2 ** attempt * 3
                print(f"  [github] network error ({e.__class__.__name__}) — retrying in {wait}s...")
                time.sleep(wait)
        return None

    def _wait_for_rate_limit(self, headers):
        remaining = int(headers.get("X-RateLimit-Remaining", 1))
        reset_at = int(headers.get("X-RateLimit-Reset", time.time() + 60))
        if remaining < 5:
            wait = max(reset_at - time.time() + 2, 5)
            print(f"  [github] rate limit — waiting {wait:.0f}s...")
            time.sleep(wait)

    def _search_users(self, query):
        results, page = [], 1
        while True:
            resp = self._gh_get(
                "https://api.github.com/search/users",
                params={"q": query, "per_page": 100, "page": page},
            )
            if resp is None or resp.status_code == 422:
                break
            if resp.status_code != 200:
                time.sleep(10)
                continue
            data = resp.json()
            items = data.get("items", [])
            results.extend(items)
            total = data.get("total_count", 0)
            if not items or len(results) >= min(total, 1000):
                break
            page += 1
            time.sleep(2)
        return results

    def _get_profile(self, username):
        resp = self._gh_get(f"https://api.github.com/users/{username}")
        return resp.json() if resp and resp.status_code == 200 else None

    def _get_commit_email(self, username):
        repos = self._gh_get(
            f"https://api.github.com/users/{username}/repos",
            params={"sort": "pushed", "per_page": 10, "type": "owner"},
        )
        if not repos or repos.status_code != 200:
            return None
        for repo in repos.json():
            if repo.get("fork") or repo.get("private"):
                continue
            commits = self._gh_get(
                f"https://api.github.com/repos/{username}/{repo['name']}/commits",
                params={"author": username, "per_page": 1},
            )
            if not commits or commits.status_code != 200:
                continue
            data = commits.json()
            if not data:
                continue
            email = data[0].get("commit", {}).get("author", {}).get("email", "")
            if self.is_valid_email(email):
                return email
            time.sleep(0.5)
        return None

    # ── Public interface ──────────────────────────────────────────────────

    def scrape(self, seen_emails: set, seen_usernames: set) -> list[dict]:
        leads = []

        for query in self.queries:
            print(f"\n[github] Query: {query}")
            users = self._search_users(query)
            print(f"[github] Found {len(users)} users")

            for u in users:
                username = u["login"]
                if username.lower() in seen_usernames:
                    continue
                seen_usernames.add(username.lower())

                profile = self._get_profile(username)
                if not profile or profile.get("type") != "User":
                    continue

                name      = profile.get("name") or username
                email     = profile.get("email", "")
                company   = (profile.get("company") or "").strip().lstrip("@")
                bio       = (profile.get("bio") or "").strip().replace("\n", " ")
                website   = profile.get("blog") or ""
                twitter   = profile.get("twitter_username") or ""
                followers = profile.get("followers", 0)

                source = "profile"
                if not self.is_valid_email(email):
                    email = self._get_commit_email(username) or ""
                    source = "commit"

                if not self.is_valid_email(email):
                    print(f"  SKIP {username} — no email")
                    continue
                if email.lower() in seen_emails:
                    print(f"  DUPE {username} — duplicate email")
                    continue

                seen_emails.add(email.lower())
                leads.append({
                    "Name":      name,
                    "Username":  username,
                    "Email":     email,
                    "Company":   company,
                    "Bio":       bio[:200],
                    "Website":   website,
                    "Twitter":   twitter,
                    "Followers": followers,
                    "Source":    f"github-{source}",
                    "Profile":   f"https://github.com/{username}",
                })
                print(f"  FOUND {name} <{email}> [{source}] ({followers} followers)")
                time.sleep(0.3)

        return leads
