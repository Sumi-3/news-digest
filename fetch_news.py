import feedparser
import os
import requests
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── 日本語ニュースソース (RSS) ──────────────────────────────────────────────
FEEDS = {
    "テクノロジー・IT": [
        "https://rss.itmedia.co.jp/rss/2.0/itmabiz.xml",
        "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml",
        "https://jp.techcrunch.com/feed/",
    ],
    "ビジネス・経済": [
        "https://www.nikkei.com/rss/",
        "https://zaikei.co.jp/rss/all.rss",
        "https://feeds.feedburner.com/businessinsider-japan",
    ],
}

MAX_ARTICLES_PER_FEED = 4


# ─── 記事取得 ─────────────────────────────────────────────────────────────────
def fetch_articles():
    by_cat = {}
    for category, urls in FEEDS.items():
        by_cat[category] = []
        for url in urls:
            try:
                feed = feedparser.parse(url)
                source = feed.feed.get("title", url)
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    by_cat[category].append({
                        "title":   entry.get("title", "").strip(),
                        "summary": entry.get("summary", "")[:400].strip(),
                        "link":    entry.get("link", ""),
                        "source":  source,
                    })
            except Exception as e:
                print(f"[WARN] {url}: {e}")
        print(f"[OK] {category}: {len(by_cat[category])} 件")
    return by_cat


# ─── Gemini API で初学者向け要約 ─────────────────────────────────────────────
def summarize_with_gemini(title: str, summary: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return summary  # APIキーがなければ元の概要をそのまま返す

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )

    prompt = f"""以下のニュース記事を、ITやビジネスの知識がない初学者にも分かるように説明してください。

条件：
- 専門用語は使わず、中学生でも理解できる言葉で書く
- 難しい言葉を使う場合はカッコ内で一言説明を加える
- 「なぜこれが重要なのか」を一言添える
- 3文以内でまとめる

タイトル: {title}
記事概要: {summary}"""

    try:
        resp = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=15,
        )
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"[WARN] Gemini API error: {e}")
        return summary  # エラー時は元の概要を返す


# ─── HTML 生成 ────────────────────────────────────────────────────────────────
def generate_html(by_cat: dict) -> None:
    jst      = timezone(timedelta(hours=9))
    now      = datetime.now(jst)
    date_str = now.strftime("%Y年%m月%d日")
    ts_str   = now.strftime("%Y-%m-%d %H:%M JST")

    sections_html = ""
    for cat, articles in by_cat.items():
        sections_html += f'<section class="category"><h2>{cat}</h2>\n'
        for a in articles:
            original = a["summary"].replace("<", "&lt;").replace(">", "&gt;")
            gemini   = a.get("gemini_summary", "").replace("<", "&lt;").replace(">", "&gt;")
            sections_html += f"""  <article class="card">
    <div class="source">{a['source']}</div>
    <h3><a href="{a['link']}" target="_blank" rel="noopener">{a['title']}</a></h3>
    <div class="badge">🤖 AI解説</div>
    <p class="ai-summary">{gemini}</p>
    <details>
      <summary>元の記事概要を見る</summary>
      <p class="original">{original}</p>
    </details>
  </article>\n"""
        sections_html += "</section>\n"

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily News — {date_str}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8;
    --green: #34d399;
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
  .card h3 {{ font-size: .97rem; margin-bottom: .6rem; font-weight: 600; }}
  .card h3 a {{ color: var(--text); text-decoration: none; }}
  .card h3 a:hover {{ color: var(--accent); }}
  .badge {{
    display: inline-block; font-size: .7rem; padding: .15rem .5rem;
    background: rgba(52,211,153,.15); color: var(--green);
    border: 1px solid rgba(52,211,153,.3); border-radius: 4px; margin-bottom: .5rem;
  }}
  .ai-summary {{ font-size: .92rem; color: var(--text); margin-bottom: .8rem; line-height: 1.75; }}
  details {{ margin-top: .4rem; }}
  details summary {{
    font-size: .78rem; color: var(--muted); cursor: pointer;
    list-style: none; display: flex; align-items: center; gap: .3rem;
  }}
  details summary::before {{ content: "▶"; font-size: .65rem; transition: transform .2s; }}
  details[open] summary::before {{ transform: rotate(90deg); }}
  .original {{ font-size: .82rem; color: var(--muted); margin-top: .5rem; padding-top: .5rem; border-top: 1px solid var(--border); }}
  footer {{ text-align: center; padding: 2rem; color: #475569; font-size: .8rem; border-top: 1px solid var(--border); }}
</style>
</head>
<body>
<header>
  <h1>📰 Daily News</h1>
  <p>{date_str} — Gemini AI が初学者向けに解説</p>
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
    print("[OK] docs/index.html 生成完了")


# ─── Telegram 通知 ────────────────────────────────────────────────────────────
def send_telegram(by_cat: dict, page_url: str) -> None:
    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    jst      = timezone(timedelta(hours=9))
    date_str = datetime.now(jst).strftime("%Y/%m/%d")

    lines = [f"📰 *{date_str} ニュースまとめ*\n"]
    for cat, articles in by_cat.items():
        lines.append(f"*{cat}*")
        for a in articles[:3]:
            title = a["title"].replace("*", "\\*").replace("[", "\\[").replace("]", "\\]")
            lines.append(f"• [{title}]({a['link']})")
        lines.append("")

    lines.append(f"🔗 [AI解説つき全記事を読む]({page_url})")

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
        print("[OK] Telegram 通知送信完了")
    else:
        print(f"[ERROR] Telegram: {resp.status_code} {resp.text}")


# ─── エントリーポイント ────────────────────────────────────────────────────────
if __name__ == "__main__":
    page_url = os.environ.get("PAGE_URL", "https://YOUR_USERNAME.github.io/news-digest/")

    print("=== Step 1: 記事取得 ===")
    by_cat = fetch_articles()

    print("=== Step 2: Gemini で要約 ===")
    total = sum(len(v) for v in by_cat.values())
    count = 0
    for cat, articles in by_cat.items():
        for a in articles:
            count += 1
            print(f"  [{count}/{total}] {a['title'][:40]}...")
            a["gemini_summary"] = summarize_with_gemini(a["title"], a["summary"])

    print("=== Step 3: HTML 生成 ===")
    generate_html(by_cat)

    print("=== Step 4: Telegram 通知 ===")
    send_telegram(by_cat, page_url)

    print("=== 完了 ===")
import feedparser
import os
import requests
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── 日本語ニュースソース (RSS) ──────────────────────────────────────────────
FEEDS = {
    "テクノロジー・IT": [
        "https://rss.itmedia.co.jp/rss/2.0/itmabiz.xml",
        "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml",
        "https://jp.techcrunch.com/feed/",
    ],
    "ビジネス・経済": [
        "https://www.nikkei.com/rss/",
        "https://zaikei.co.jp/rss/all.rss",
        "https://feeds.feedburner.com/businessinsider-japan",
    ],
}

MAX_ARTICLES_PER_FEED = 4


# ─── 記事取得 ─────────────────────────────────────────────────────────────────
def fetch_articles():
    by_cat = {}
    for category, urls in FEEDS.items():
        by_cat[category] = []
        for url in urls:
            try:
                feed = feedparser.parse(url)
                source = feed.feed.get("title", url)
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    by_cat[category].append({
                        "title":   entry.get("title", "").strip(),
                        "summary": entry.get("summary", "")[:400].strip(),
                        "link":    entry.get("link", ""),
                        "source":  source,
                    })
            except Exception as e:
                print(f"[WARN] {url}: {e}")
        print(f"[OK] {category}: {len(by_cat[category])} 件")
    return by_cat


# ─── Gemini API で初学者向け要約 ─────────────────────────────────────────────
def summarize_with_gemini(title: str, summary: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return summary  # APIキーがなければ元の概要をそのまま返す

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )

    prompt = f"""以下のニュース記事を、ITやビジネスの知識がない初学者にも分かるように説明してください。

条件：
- 専門用語は使わず、中学生でも理解できる言葉で書く
- 難しい言葉を使う場合はカッコ内で一言説明を加える
- 「なぜこれが重要なのか」を一言添える
- 3文以内でまとめる

タイトル: {title}
記事概要: {summary}"""

    try:
        resp = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=15,
        )
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"[WARN] Gemini API error: {e}")
        return summary  # エラー時は元の概要を返す


# ─── HTML 生成 ────────────────────────────────────────────────────────────────
def generate_html(by_cat: dict) -> None:
    jst      = timezone(timedelta(hours=9))
    now      = datetime.now(jst)
    date_str = now.strftime("%Y年%m月%d日")
    ts_str   = now.strftime("%Y-%m-%d %H:%M JST")

    sections_html = ""
    for cat, articles in by_cat.items():
        sections_html += f'<section class="category"><h2>{cat}</h2>\n'
        for a in articles:
            original = a["summary"].replace("<", "&lt;").replace(">", "&gt;")
            gemini   = a.get("gemini_summary", "").replace("<", "&lt;").replace(">", "&gt;")
            sections_html += f"""  <article class="card">
    <div class="source">{a['source']}</div>
    <h3><a href="{a['link']}" target="_blank" rel="noopener">{a['title']}</a></h3>
    <div class="badge">🤖 AI解説</div>
    <p class="ai-summary">{gemini}</p>
    <details>
      <summary>元の記事概要を見る</summary>
      <p class="original">{original}</p>
    </details>
  </article>\n"""
        sections_html += "</section>\n"

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily News — {date_str}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8;
    --green: #34d399;
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
  .card h3 {{ font-size: .97rem; margin-bottom: .6rem; font-weight: 600; }}
  .card h3 a {{ color: var(--text); text-decoration: none; }}
  .card h3 a:hover {{ color: var(--accent); }}
  .badge {{
    display: inline-block; font-size: .7rem; padding: .15rem .5rem;
    background: rgba(52,211,153,.15); color: var(--green);
    border: 1px solid rgba(52,211,153,.3); border-radius: 4px; margin-bottom: .5rem;
  }}
  .ai-summary {{ font-size: .92rem; color: var(--text); margin-bottom: .8rem; line-height: 1.75; }}
  details {{ margin-top: .4rem; }}
  details summary {{
    font-size: .78rem; color: var(--muted); cursor: pointer;
    list-style: none; display: flex; align-items: center; gap: .3rem;
  }}
  details summary::before {{ content: "▶"; font-size: .65rem; transition: transform .2s; }}
  details[open] summary::before {{ transform: rotate(90deg); }}
  .original {{ font-size: .82rem; color: var(--muted); margin-top: .5rem; padding-top: .5rem; border-top: 1px solid var(--border); }}
  footer {{ text-align: center; padding: 2rem; color: #475569; font-size: .8rem; border-top: 1px solid var(--border); }}
</style>
</head>
<body>
<header>
  <h1>📰 Daily News</h1>
  <p>{date_str} — Gemini AI が初学者向けに解説</p>
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
    print("[OK] docs/index.html 生成完了")


# ─── Telegram 通知 ────────────────────────────────────────────────────────────
def send_telegram(by_cat: dict, page_url: str) -> None:
    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    jst      = timezone(timedelta(hours=9))
    date_str = datetime.now(jst).strftime("%Y/%m/%d")

    lines = [f"📰 *{date_str} ニュースまとめ*\n"]
    for cat, articles in by_cat.items():
        lines.append(f"*{cat}*")
        for a in articles[:3]:
            title = a["title"].replace("*", "\\*").replace("[", "\\[").replace("]", "\\]")
            lines.append(f"• [{title}]({a['link']})")
        lines.append("")

    lines.append(f"🔗 [AI解説つき全記事を読む]({page_url})")

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
        print("[OK] Telegram 通知送信完了")
    else:
        print(f"[ERROR] Telegram: {resp.status_code} {resp.text}")


# ─── エントリーポイント ────────────────────────────────────────────────────────
if __name__ == "__main__":
    page_url = os.environ.get("PAGE_URL", "https://YOUR_USERNAME.github.io/news-digest/")

    print("=== Step 1: 記事取得 ===")
    by_cat = fetch_articles()

    print("=== Step 2: Gemini で要約 ===")
    total = sum(len(v) for v in by_cat.values())
    count = 0
    for cat, articles in by_cat.items():
        for a in articles:
            count += 1
            print(f"  [{count}/{total}] {a['title'][:40]}...")
            a["gemini_summary"] = summarize_with_gemini(a["title"], a["summary"])

    print("=== Step 3: HTML 生成 ===")
    generate_html(by_cat)

    print("=== Step 4: Telegram 通知 ===")
    send_telegram(by_cat, page_url)

    print("=== 完了 ===")
