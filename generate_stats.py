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
def bar(pct, color, y_offset):
    w = max(pct * 220, 2)
    return (
        f'<rect x="0" y="{y_offset}" width="{w:.1f}" height="8" rx="4" '
        f'fill="{color}" opacity="0.9"/>'
    )

def esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def generate_svg(s):
    langs        = s["top_langs"]
    total_bytes  = s["total_bytes"]

    # Build language rows
    lang_rows = ""
    bar_rows  = ""
    y_start   = 198

    for i, (name, size, color) in enumerate(langs):
        pct     = size / total_bytes
        pct_txt = f"{pct*100:.1f}%"
        y       = y_start + i * 28

        # dot + name
        lang_rows += (
            f'<circle cx="10" cy="{y+4}" r="5" fill="{color}"/>'
            f'<text x="22" y="{y+8}" font-size="11.5" fill="#c9d1d9">{esc(name)}</text>'
            f'<text x="230" y="{y+8}" font-size="11" fill="#8b949e" text-anchor="end">{pct_txt}</text>'
        )
        # bar
        bar_rows += (
            f'<rect x="0" y="{y+14}" width="230" height="6" rx="3" fill="#21262d"/>'
            + bar(pct, color, y + 14)
        )

    lang_section_h = len(langs) * 28 + 10
    total_h = 195 + lang_section_h + 20   # dynamic height

    # Stats row items
    stats = [
        ("⭐", "Stars",    s["stars"]),
        ("🍴", "Forks",    s["forks"]),
        ("📦", "Repos",    s["repos"]),
        ("👥", "Followers",s["followers"]),
        ("💻", "Commits",  s["commits"]),
        ("🔀", "PRs",      s["prs"]),
    ]

    stat_items = ""
    cols = 3
    cell_w = 240 / cols
    for idx, (icon, label, val) in enumerate(stats):
        cx = (idx % cols) * cell_w + cell_w / 2
        cy = 70 + (idx // cols) * 52
        stat_items += (
            f'<text x="{cx:.0f}" y="{cy}" font-size="18" text-anchor="middle">{icon}</text>'
            f'<text x="{cx:.0f}" y="{cy+18}" font-size="13" font-weight="bold" '
            f'fill="#e6edf3" text-anchor="middle">{val:,}</text>'
            f'<text x="{cx:.0f}" y="{cy+32}" font-size="10" fill="#8b949e" text-anchor="middle">{label}</text>'
        )

    svg = f"""<svg width="480" height="{total_h}" viewBox="0 0 480 {total_h}"
     xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     role="img" aria-label="GitHub Stats for {esc(s['login'])}">

  <defs>
    <linearGradient id="grad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%"   stop-color="#0d1117"/>
      <stop offset="100%" stop-color="#161b22"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%"   stop-color="#58a6ff"/>
      <stop offset="100%" stop-color="#bc8cff"/>
    </linearGradient>
    <clipPath id="clip-card">
      <rect width="480" height="{total_h}" rx="14"/>
    </clipPath>
    <filter id="shadow">
      <feDropShadow dx="0" dy="4" stdDeviation="8" flood-color="#010409" flood-opacity="0.6"/>
    </filter>
  </defs>

  <!-- Card background -->
  <g clip-path="url(#clip-card)" filter="url(#shadow)">
    <rect width="480" height="{total_h}" fill="url(#grad)"/>

    <!-- Accent stripe top -->
    <rect width="480" height="3" fill="url(#accent)"/>

    <!-- ── LEFT PANEL: Stats ─────────────────────────────────────── -->
    <g transform="translate(20, 20)">

      <!-- Username + name -->
      <text x="0" y="22" font-size="15" font-weight="700" fill="url(#accent)"
            font-family="'Segoe UI', 'Helvetica Neue', Arial, sans-serif">@{esc(s['login'])}</text>
      <text x="0" y="40" font-size="11" fill="#8b949e"
            font-family="'Segoe UI', 'Helvetica Neue', Arial, sans-serif">{esc(s['name'])} · {s['year']} Contributions: {s['total_contribs']:,}</text>

      <!-- Divider -->
      <rect x="0" y="50" width="240" height="1" fill="#21262d"/>

      <!-- Stats grid -->
      {stat_items}

      <!-- Divider 2 -->
      <rect x="0" y="175" width="240" height="1" fill="#21262d"/>

      <!-- Issues & Reviews -->
      <text x="0"   y="192" font-size="11" fill="#8b949e">Issues opened</text>
      <text x="240" y="192" font-size="11" fill="#c9d1d9" text-anchor="end" font-weight="600">{s['issues']}</text>
      <text x="0"   y="208" font-size="11" fill="#8b949e">PR Reviews</text>
      <text x="240" y="208" font-size="11" fill="#c9d1d9" text-anchor="end" font-weight="600">{s['reviews']}</text>

    </g>

    <!-- Vertical divider -->
    <rect x="285" y="20" width="1" height="{total_h - 40}" fill="#21262d"/>

    <!-- ── RIGHT PANEL: Languages ─────────────────────────────────── -->
    <g transform="translate(305, 20)">

      <text x="0" y="18" font-size="13" font-weight="700" fill="#e6edf3"
            font-family="'Segoe UI', 'Helvetica Neue', Arial, sans-serif">Top Languages</text>
      <rect x="0" y="26" width="155" height="2" fill="url(#accent)" rx="1"/>

      <!-- Combined bar -->
      <g transform="translate(0, 40)">
        <rect width="155" height="10" rx="5" fill="#21262d"/>"""

    # combined bar segments
    cx = 0.0
    for name, size, color in langs:
        pct = size / total_bytes
        w   = max(pct * 155, 1.5)
        svg += f'\n        <rect x="{cx:.1f}" y="0" width="{w:.1f}" height="10" fill="{color}"/>'
        cx += w

    svg += f"""
      </g>

      <!-- Language list -->
      <g transform="translate(0, 65)">"""

    for i, (name, size, color) in enumerate(langs):
        pct     = size / total_bytes
        pct_txt = f"{pct*100:.1f}%"
        y       = i * 28
        svg += f"""
        <circle cx="6" cy="{y+6}" r="5" fill="{color}"/>
        <text x="16" y="{y+11}" font-size="11" fill="#c9d1d9"
              font-family="'Segoe UI', sans-serif">{esc(name)}</text>
        <text x="155" y="{y+11}" font-size="10.5" fill="#8b949e" text-anchor="end">{pct_txt}</text>
        <rect x="0" y="{y+16}" width="155" height="5" rx="2.5" fill="#21262d"/>
        <rect x="0" y="{y+16}" width="{max(pct*155, 2):.1f}" height="5" rx="2.5" fill="{color}" opacity="0.85"/>"""

    svg += f"""
      </g>

    </g>

    <!-- Footer -->
    <text x="240" y="{total_h - 8}" font-size="9" fill="#484f58" text-anchor="middle"
          font-family="'Segoe UI', sans-serif">Auto-generated · github.com/{esc(s['login'])}</text>

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
