"""
Product Hunt source
===================
Scrapes Product Hunt makers via the GraphQL API v2, then resolves their
email addresses through GitHub.

API limitation (developer token)
---------------------------------
With a free developer token the PH API masks most team-member fields —
only the *primary* maker of each post gets a real username; all others
return a shared placeholder with id "0".  In practice this yields roughly
1 real lead per 50 posts.  Use more topics / pages to compensate.

Get your token:
  producthunt.com/v2/oauth/applications → create app → Developer Token
"""

import os
import re
import time
import requests

from .base import LeadSource


# ── GraphQL queries ───────────────────────────────────────────────────────

_TOPIC_QUERY = """
query getPosts($topic: String!, $cursor: String) {
  posts(first: 50, topic: $topic, after: $cursor, order: RANKING) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        name
        votesCount
        makers {
          id
          name
          username
          headline
          websiteUrl
          twitterUsername
        }
      }
    }
  }
}
"""

_TOP_QUERY = """
query getTopPosts($cursor: String) {
  posts(first: 50, after: $cursor, order: VOTES, featured: true) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        name
        votesCount
        makers {
          id
          name
          username
          headline
          websiteUrl
          twitterUsername
        }
      }
    }
  }
}
"""

_PH_API = "https://api.producthunt.com/v2/api/graphql"

# Sentinel: PH returns this id for masked / restricted maker records
_MASKED_ID = "0"


class ProductHuntSource(LeadSource):
    """Collect leads from Product Hunt makers."""

    def __init__(self, config: dict):
        self.config    = config
        cfg            = config.get("sources", {}).get("producthunt", {})
        self.ph_token  = os.getenv(cfg.get("token_env", "PRODUCTHUNT_TOKEN"), "")
        self.gh_token  = os.getenv(
            config.get("sources", {}).get("github", {}).get("token_env", "GITHUB_TOKEN"), ""
        )
        self.topics    = cfg.get("topics", [
            "developer-tools",
            "artificial-intelligence",
            "productivity",
            "marketing",
            "developer-tools",
            "no-code",
            "open-source",
        ])
        self.min_votes  = cfg.get("min_votes", 10)
        self.pages_per_topic = cfg.get("pages_per_topic", 5)
        self._ph_headers = {
            "Authorization": f"Bearer {self.ph_token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }
        self._gh_headers = {
            "Authorization": f"token {self.gh_token}",
            "Accept":        "application/vnd.github.v3+json",
        }

    # ── Public interface ──────────────────────────────────────────────────

    def scrape(self, seen_emails: set, seen_usernames: set) -> list[dict]:
        if not self.ph_token:
            print("  [producthunt] PRODUCTHUNT_TOKEN not set — skipping")
            return []

        makers_map = self._collect_makers()
        print(f"  [producthunt] {len(makers_map)} unique makers found across all topics")

        leads = []
        for ph_username, maker in makers_map.items():
            ph_key = f"ph:{ph_username.lower()}"
            if ph_key in seen_usernames:
                continue
            seen_usernames.add(ph_key)

            gh_username = self._extract_github_username(maker)
            if not gh_username:
                print(f"  SKIP {ph_username} — no GitHub link")
                continue

            if gh_username.lower() in seen_usernames:
                print(f"  DUPE {ph_username} — GitHub user already in leads")
                continue

            email, gh_profile = self._get_github_email(gh_username)

            if not self.is_valid_email(email):
                print(f"  SKIP {ph_username} — no email (gh: {gh_username})")
                seen_usernames.add(gh_username.lower())
                continue

            if email.lower() in seen_emails:
                print(f"  DUPE {ph_username} — duplicate email")
                seen_usernames.add(gh_username.lower())
                continue

            seen_usernames.add(gh_username.lower())
            seen_emails.add(email.lower())

            name     = maker.get("name") or gh_username
            bio      = (maker.get("headline") or "").strip()
            if gh_profile:
                bio = bio or (gh_profile.get("bio") or "").strip().replace("\n", " ")
            company  = ((gh_profile.get("company") or "").strip().lstrip("@")
                        if gh_profile else "")
            website  = (maker.get("websiteUrl")
                        or (gh_profile.get("blog") if gh_profile else "")
                        or "")
            twitter  = (maker.get("twitterUsername")
                        or (gh_profile.get("twitter_username") if gh_profile else "")
                        or "")
            followers = gh_profile.get("followers", 0) if gh_profile else 0
            product   = maker.get("_product", "")

            leads.append({
                "Name":      name,
                "Username":  ph_username,
                "Email":     email,
                "Company":   company,
                "Bio":       bio[:200],
                "Website":   website,
                "Twitter":   twitter,
                "Followers": followers,
                "Source":    "producthunt",
                "Profile":   f"https://www.producthunt.com/@{ph_username}",
            })
            print(f"  FOUND {name} <{email}> (maker of {product}, {maker['_votes']} votes)")
            time.sleep(0.5)

        return leads

    # ── Collection helpers ────────────────────────────────────────────────

    def _collect_makers(self) -> dict:
        """Return {ph_username: maker_dict} across all configured topics."""
        all_makers: dict = {}

        # Try topic-based queries first
        test = self._get_topic_makers(self.topics[0], max_pages=1)
        if len(test) >= 2:
            # Topic filter is returning real data — run all topics
            all_makers.update(test)
            for topic in self.topics[1:]:
                print(f"  topic: {topic}")
                found = self._get_topic_makers(topic, max_pages=self.pages_per_topic)
                all_makers.update(found)
                time.sleep(1)
        else:
            # Developer token masking is aggressive — fall back to top posts
            print("  [producthunt] Topic filter sparse; using top all-time posts")
            all_makers = self._get_top_makers()

        return all_makers

    def _get_topic_makers(self, topic: str, max_pages: int = 5) -> dict:
        makers: dict = {}
        cursor = None

        for _ in range(max_pages):
            variables: dict = {"topic": topic}
            if cursor:
                variables["cursor"] = cursor

            resp = self._ph_post(_TOPIC_QUERY, variables)
            if not resp:
                break

            data  = resp.get("data", {}).get("posts", {})
            edges = data.get("edges", [])
            makers.update(self._extract_makers(edges))

            pi = data.get("pageInfo", {})
            if not pi.get("hasNextPage") or not edges:
                break
            cursor = pi.get("endCursor")
            time.sleep(2)

        return makers

    def _get_top_makers(self, max_pages: int = 10) -> dict:
        makers: dict = {}
        cursor = None

        for _ in range(max_pages):
            variables: dict = {}
            if cursor:
                variables["cursor"] = cursor

            resp = self._ph_post(_TOP_QUERY, variables)
            if not resp:
                break

            data  = resp.get("data", {}).get("posts", {})
            edges = data.get("edges", [])
            makers.update(self._extract_makers(edges))

            pi = data.get("pageInfo", {})
            if not pi.get("hasNextPage") or not edges:
                break
            cursor = pi.get("endCursor")
            time.sleep(2)

        return makers

    def _extract_makers(self, edges: list) -> dict:
        """Return unique makers with sufficient votes and a real (non-masked) username."""
        makers: dict = {}
        for edge in edges:
            post  = edge.get("node", {})
            votes = post.get("votesCount", 0)
            if votes < self.min_votes:
                continue
            product = post.get("name", "")
            for maker in post.get("makers", []):
                # Skip placeholder records returned for masked team members
                if maker.get("id") == _MASKED_ID:
                    continue
                uname = maker.get("username")
                if uname and uname not in makers:
                    makers[uname] = {
                        **maker,
                        "_product": product,
                        "_votes":   votes,
                    }
        return makers

    # ── GitHub email resolution ───────────────────────────────────────────

    @staticmethod
    def _extract_github_username(maker: dict) -> str | None:
        website  = maker.get("websiteUrl") or ""
        headline = maker.get("headline")  or ""
        ph_user  = maker.get("username")  or ""

        for text in (website, headline):
            m = re.search(r"github\.com/([a-zA-Z0-9_-]+)", text)
            if m:
                return m.group(1)

        return ph_user or None

    def _get_github_email(self, gh_username: str) -> tuple[str | None, dict | None]:
        resp = self._gh_get(f"https://api.github.com/users/{gh_username}")
        gh_profile = None

        if resp and resp.status_code == 200:
            gh_profile = resp.json()
            if gh_profile.get("type") != "User":
                return None, None
            email = gh_profile.get("email", "")
            if self.is_valid_email(email):
                return email, gh_profile

        # Commit history fallback
        repos = self._gh_get(
            f"https://api.github.com/users/{gh_username}/repos",
            params={"sort": "pushed", "per_page": 10, "type": "owner"},
        )
        if not repos or repos.status_code != 200:
            return None, gh_profile

        for repo in (repos.json() or []):
            if repo.get("fork") or repo.get("private"):
                continue
            commits = self._gh_get(
                f"https://api.github.com/repos/{gh_username}/{repo['name']}/commits",
                params={"author": gh_username, "per_page": 1},
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

    # ── HTTP helpers ──────────────────────────────────────────────────────

    def _ph_post(self, query: str, variables: dict, retries: int = 4) -> dict | None:
        for attempt in range(retries):
            try:
                resp = requests.post(
                    _PH_API,
                    json={"query": query, "variables": variables},
                    headers=self._ph_headers,
                    timeout=20,
                )
                if resp.status_code == 429:
                    reset_in = resp.json().get("errors", [{}])[0].get(
                        "details", {}
                    ).get("reset_in", 60)
                    wait = min(int(reset_in) + 5, 120)
                    print(f"  [PH rate limit] waiting {wait}s...")
                    time.sleep(wait)
                    continue
                if resp.status_code != 200:
                    print(f"  [PH] HTTP {resp.status_code}")
                    return None
                body = resp.json()
                if body.get("errors"):
                    print(f"  [PH] error: {body['errors'][0].get('message')}")
                    return None
                return body
            except Exception as exc:
                wait = 2 ** attempt * 3
                print(f"  [PH] {exc.__class__.__name__} — retry in {wait}s")
                time.sleep(wait)
        return None

    def _gh_get(self, url: str, params: dict | None = None, retries: int = 4):
        for attempt in range(retries):
            try:
                resp = requests.get(
                    url, headers=self._gh_headers, params=params, timeout=20
                )
                remaining = int(resp.headers.get("X-RateLimit-Remaining", 1))
                if remaining < 5:
                    reset_at = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
                    wait     = max(reset_at - time.time() + 2, 5)
                    print(f"  [GH rate limit] waiting {wait:.0f}s...")
                    time.sleep(wait)
                return resp
            except Exception as exc:
                wait = 2 ** attempt * 3
                print(f"  [GH] {exc.__class__.__name__} — retry in {wait}s")
                time.sleep(wait)
        return None
