import feedparser
import os
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── ニュースソース (RSS) ────────────────────────────────────────────────────
FEEDS = {
    "Technology & AI": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    ],
    "Business & Economy": [
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "https://feeds.reuters.com/reuters/businessNews",
    ],
}

MAX_ARTICLES_PER_FEED = 4  # フィードあたり最大記事数


# ─── 記事取得 ─────────────────────────────────────────────────────────────────
def fetch_articles() -> dict[str, list[dict]]:
    by_cat: dict[str, list[dict]] = {}
    for category, urls in FEEDS.items():
        by_cat[category] = []
        for url in urls:
            try:
                feed = feedparser.parse(url)
                source = feed.feed.get("title", url)
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    by_cat[category].append({
                        "title":   entry.get("title", "").strip(),
                        "summary": entry.get("summary", "")[:300].strip(),
                        "link":    entry.get("link", ""),
                        "source":  source,
                    })
            except Exception as e:
                print(f"[WARN] {url}: {e}")
        print(f"[OK] {category}: {len(by_cat[category])} articles")
    return by_cat


# ─── HTML 生成 ────────────────────────────────────────────────────────────────
def generate_html(by_cat: dict[str, list[dict]]) -> None:
    jst     = timezone(timedelta(hours=9))
    now     = datetime.now(jst)
    date_str = now.strftime("%B %d, %Y")
    ts_str   = now.strftime("%Y-%m-%d %H:%M JST")

    sections_html = ""
    for cat, articles in by_cat.items():
        sections_html += f'<section class="category"><h2>{cat}</h2>\n'
        for a in articles:
            summary = a["summary"].replace("<", "&lt;").replace(">", "&gt;")
            sections_html += f"""  <article class="card">
    <div class="source">{a['source']}</div>
    <h3><a href="{a['link']}" target="_blank" rel="noopener">{a['title']}</a></h3>
    <p>{summary}</p>
  </article>\n"""
        sections_html += "</section>\n"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily News — {date_str}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8;
    --font: 'Segoe UI', 'Hiragino Sans', sans-serif;
  }}
  body {{ font-family: var(--font); background: var(--bg); color: var(--text); line-height: 1.7; }}
  header {{
    background: linear-gradient(160deg, #1e3a5f 0%, #0f172a 100%);
    padding: 2.5rem 1rem 2rem; text-align: center;
    border-bottom: 1px solid var(--border);
  }}
  header h1 {{ font-size: 2rem; color: var(--accent); letter-spacing: -0.02em; }}
  header p  {{ color: var(--muted); margin-top: .4rem; font-size: .95rem; }}
  main {{ max-width: 860px; margin: 2.5rem auto; padding: 0 1rem 4rem; }}
  .category {{ margin-bottom: 3rem; }}
  .category h2 {{
    color: var(--accent); border-left: 3px solid var(--accent);
    padding-left: .75rem; margin-bottom: 1.2rem;
    letter-spacing: .06em; text-transform: uppercase; font-size: .8rem;
  }}
  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.1rem 1.4rem; margin-bottom: .8rem;
    transition: border-color .15s, transform .15s;
  }}
  .card:hover {{ border-color: var(--accent); transform: translateY(-1px); }}
  .source {{ font-size: .72rem; color: var(--accent); opacity: .7; text-transform: uppercase; letter-spacing: .05em; margin-bottom: .3rem; }}
  .card h3 {{ font-size: .97rem; margin-bottom: .4rem; font-weight: 600; }}
  .card h3 a {{ color: var(--text); text-decoration: none; }}
  .card h3 a:hover {{ color: var(--accent); }}
  .card p {{ color: var(--muted); font-size: .87rem; }}
  footer {{ text-align: center; padding: 2rem; color: #475569; font-size: .8rem; border-top: 1px solid var(--border); }}
</style>
</head>
<body>
<header>
  <h1>📰 Daily News</h1>
  <p>{date_str} — Auto-collected via RSS</p>
</header>
<main>
{sections_html}
</main>
<footer>Updated automatically via GitHub Actions &nbsp;·&nbsp; {ts_str}</footer>
</body>
</html>"""

    Path("docs").mkdir(exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("[OK] docs/index.html generated")


# ─── Telegram 通知 ────────────────────────────────────────────────────────────
def send_telegram(by_cat: dict[str, list[dict]], page_url: str) -> None:
    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    jst      = timezone(timedelta(hours=9))
    date_str = datetime.now(jst).strftime("%Y/%m/%d")

    lines = [f"📰 *{date_str} News Digest*\n"]
    for cat, articles in by_cat.items():
        lines.append(f"*{cat}*")
        for a in articles[:3]:
            title = a["title"].replace("*", "\\*").replace("[", "\\[").replace("]", "\\]")
            lines.append(f"• [{title}]({a['link']})")
        lines.append("")

    lines.append(f"🔗 [Read all articles]({page_url})")

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": "\n".join(lines),
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=10,
    )
    if resp.ok:
        print("[OK] Telegram notification sent")
    else:
        print(f"[ERROR] Telegram: {resp.status_code} {resp.text}")


# ─── エントリーポイント ────────────────────────────────────────────────────────
if __name__ == "__main__":
    page_url = os.environ.get(
        "PAGE_URL",
        "https://YOUR_USERNAME.github.io/news-digest/"
    )

    print("=== Step 1: Fetching articles ===")
    by_cat = fetch_articles()

    print("=== Step 2: Generating HTML ===")
    generate_html(by_cat)

    print("=== Step 3: Sending Telegram notification ===")
    send_telegram(by_cat, page_url)

    print("=== Done! ===")
