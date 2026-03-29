#!/usr/bin/env python3
"""
GitHub Profile Stats Generator
Fetches stats via GitHub GraphQL API and generates a beautiful SVG card.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime

# ─── CONFIG ────────────────────────────────────────────────────────────────────
GITHUB_TOKEN = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
USERNAME     = os.environ.get("GITHUB_USERNAME", "")
OUTPUT_FILE  = os.environ.get("OUTPUT_FILE", "github-stats.svg")

LANG_COLORS = {
    "Python":      "#3572A5", "JavaScript": "#f1e05a", "TypeScript":  "#2b7489",
    "Java":        "#b07219", "C++":        "#f34b7d", "C":           "#555555",
    "C#":          "#178600", "Go":         "#00ADD8", "Rust":        "#dea584",
    "Ruby":        "#701516", "PHP":        "#4F5D95", "Swift":       "#ffac45",
    "Kotlin":      "#F18E33", "Shell":      "#89e051", "HTML":        "#e34c26",
    "CSS":         "#563d7c", "Dart":       "#00B4AB", "R":           "#198CE7",
    "Scala":       "#c22d40", "Lua":        "#000080", "Vim script":  "#199f4b",
    "Haskell":     "#5e5086", "Elixir":     "#6e4a7e", "MATLAB":      "#e16737",
    "Jupyter Notebook": "#DA5B0B", "Vue":   "#2c3e50", "Dockerfile":  "#384d54",
}

DEFAULT_COLOR = "#8b949e"

# ─── GRAPHQL QUERY ─────────────────────────────────────────────────────────────
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    name
    login
    avatarUrl
    bio
    followers { totalCount }
    following  { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      nodes {
        stargazerCount
        forkCount
        primaryLanguage { name }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      contributionCalendar { totalContributions }
    }
  }
}
"""

def gql(query, variables):
    """Execute a GraphQL query against GitHub API."""
    if not GITHUB_TOKEN:
        print("ERROR: No GitHub token found. Set GH_PAT or GITHUB_TOKEN env var.", file=sys.stderr)
        sys.exit(1)

    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Content-Type":  "application/json",
            "User-Agent":    "github-stats-generator/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)

    if "errors" in data:
        print("GraphQL errors:", json.dumps(data["errors"], indent=2), file=sys.stderr)
        sys.exit(1)

    return data["data"]

def fetch_stats(username):
    now  = datetime.utcnow()
    from_ = f"{now.year}-01-01T00:00:00Z"
    to_   = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    data = gql(QUERY, {"login": username, "from": from_, "to": to_})
    user = data["user"]

    # ── Aggregate languages ────────────────────────────────────────────────────
    lang_bytes = defaultdict(int)
    lang_colors_map = {}
    total_stars = 0
    total_forks = 0

    for repo in user["repositories"]["nodes"]:
        total_stars += repo["stargazerCount"]
        total_forks += repo["forkCount"]
        for edge in repo["languages"]["edges"]:
            name  = edge["node"]["name"]
            color = edge["node"]["color"] or LANG_COLORS.get(name, DEFAULT_COLOR)
            lang_bytes[name] += edge["size"]
            lang_colors_map[name] = color

    total_bytes = sum(lang_bytes.values()) or 1
    top_langs = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)[:6]

    contribs = user["contributionsCollection"]

    return {
        "name":       user["name"] or user["login"],
        "login":      user["login"],
        "followers":  user["followers"]["totalCount"],
        "following":  user["following"]["totalCount"],
        "repos":      user["repositories"]["totalCount"],
        "stars":      total_stars,
        "forks":      total_forks,
        "commits":    contribs["totalCommitContributions"],
        "prs":        contribs["totalPullRequestContributions"],
        "issues":     contribs["totalIssueContributions"],
        "reviews":    contribs["totalPullRequestReviewContributions"],
        "total_contribs": contribs["contributionCalendar"]["totalContributions"],
        "top_langs":  [(n, lang_bytes[n], lang_colors_map[n]) for n, _ in top_langs],
        "total_bytes": total_bytes,
        "year":       now.year,
    }

# ─── SVG GENERATION ────────────────────────────────────────────────────────────
def esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def generate_svg(s):
    langs       = s["top_langs"]
    total_bytes = s["total_bytes"]

    card_w  = 340
    pad     = 28
    inner_w = card_w - pad * 2          # 284px usable width
    row_h   = 38                        # height per language row
    total_h = 70 + len(langs) * row_h + 30   # dynamic height

    # ── Combined stacked bar at top ──────────────────────────────────────────
    stacked_rects = ""
    cx = 0.0
    for name, size, color in langs:
        pct = size / total_bytes
        w   = max(pct * inner_w, 2)
        stacked_rects += f'<rect x="{cx:.1f}" y="0" width="{w:.1f}" height="12" fill="{color}"/>'
        cx += w

    # ── Per-language rows ────────────────────────────────────────────────────
    lang_rows = ""
    for i, (name, size, color) in enumerate(langs):
        pct     = size / total_bytes
        pct_txt = f"{pct * 100:.1f}%"
        y       = i * row_h
        bar_w   = max(pct * inner_w, 3)

        lang_rows += f"""
        <!-- {name} -->
        <circle cx="6" cy="{y + 7}" r="5" fill="{color}"/>
        <text x="18" y="{y + 12}" font-size="12" fill="#c9d1d9"
              font-family="'Segoe UI','Helvetica Neue',Arial,sans-serif">{esc(name)}</text>
        <text x="{inner_w}" y="{y + 12}" font-size="11" fill="#8b949e"
              text-anchor="end" font-family="'Segoe UI',sans-serif">{pct_txt}</text>
        <rect x="0" y="{y + 18}" width="{inner_w}" height="6" rx="3" fill="#21262d"/>
        <rect x="0" y="{y + 18}" width="{bar_w:.1f}" height="6" rx="3" fill="{color}" opacity="0.9"/>"""

    svg = f"""<svg width="{card_w}" height="{total_h}" viewBox="0 0 {card_w} {total_h}"
     xmlns="http://www.w3.org/2000/svg"
     role="img" aria-label="Top Languages for {esc(s['login'])}">

  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"   stop-color="#0d1117"/>
      <stop offset="100%" stop-color="#161b22"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%"   stop-color="#58a6ff"/>
      <stop offset="100%" stop-color="#bc8cff"/>
    </linearGradient>
    <clipPath id="card-clip">
      <rect width="{card_w}" height="{total_h}" rx="12"/>
    </clipPath>
  </defs>

  <g clip-path="url(#card-clip)">
    <!-- Background -->
    <rect width="{card_w}" height="{total_h}" fill="url(#bg)"/>

    <!-- Top accent stripe -->
    <rect width="{card_w}" height="3" fill="url(#accent)"/>

    <g transform="translate({pad}, 18)">

      <!-- Title -->
      <text x="0" y="16" font-size="14" font-weight="700" fill="#e6edf3"
            font-family="'Segoe UI','Helvetica Neue',Arial,sans-serif">Most Used Languages</text>
      <text x="{inner_w}" y="16" font-size="10" fill="#8b949e" text-anchor="end"
            font-family="'Segoe UI',sans-serif">@{esc(s['login'])}</text>

      <!-- Stacked bar -->
      <g transform="translate(0, 24)">
        <rect width="{inner_w}" height="12" rx="6" fill="#21262d"/>
        <clipPath id="bar-clip"><rect width="{inner_w}" height="12" rx="6"/></clipPath>
        <g clip-path="url(#bar-clip)">
          {stacked_rects}
        </g>
      </g>

      <!-- Language rows -->
      <g transform="translate(0, 48)">
        {lang_rows}
      </g>

    </g>

    <!-- Footer -->
    <text x="{card_w // 2}" y="{total_h - 7}" font-size="8.5" fill="#30363d"
          text-anchor="middle" font-family="'Segoe UI',sans-serif">
      Auto-updated via GitHub Actions
    </text>
  </g>
</svg>"""

    return svg

# ─── ENTRY POINT ───────────────────────────────────────────────────────────────
def main():
    global USERNAME
    if not USERNAME:
        if len(sys.argv) > 1:
            USERNAME = sys.argv[1]
        else:
            print("Usage: python generate_stats.py <github-username>", file=sys.stderr)
            print("   or: GITHUB_USERNAME=<username> python generate_stats.py", file=sys.stderr)
            sys.exit(1)

    print(f"Fetching stats for: {USERNAME}")
    stats = fetch_stats(USERNAME)
    print(f"  Name       : {stats['name']}")
    print(f"  Stars      : {stats['stars']}")
    print(f"  Commits    : {stats['commits']}")
    print(f"  Top langs  : {[n for n,_,_ in stats['top_langs']]}")

    svg = generate_svg(stats)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"SVG written → {OUTPUT_FILE}")

if __name__ == "__main__":
    main()