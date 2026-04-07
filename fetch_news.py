import feedparser
import os
import requests
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from bs4 import BeautifulSoup

# ─── Google News RSS URL ──────────────────────────────────────────────────────
# 元のページURL の /topics/ を /rss/topics/ に変えたもの
GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/topics/"
    "CAAqIQgKIhtDQkFTRGdvSUwyMHZNREpmTjNRU0FtcGhLQUFQAQ"
    "?hl=ja&gl=JP&ceid=JP:ja"
)

# リクエスト間の待機時間（サーバーに優しく）
REQUEST_INTERVAL = 1.5


# ─── 前日の記事かどうか判定 ───────────────────────────────────────────────────
def is_yesterday(date_str: str) -> bool:
    jst = timezone(timedelta(hours=9))
    yesterday = (datetime.now(jst) - timedelta(days=1)).date()
    try:
        dt = parsedate_to_datetime(date_str).astimezone(jst)
        return dt.date() == yesterday
    except Exception:
        return False  # 日付が取得できない場合はスキップ


# ─── 記事本文を取得（スクレイピング） ────────────────────────────────────────
def fetch_article_body(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")

        # よく使われる本文タグを優先度順に探す
        for selector in [
            "article",
            '[class*="article-body"]',
            '[class*="article_body"]',
            '[class*="content-body"]',
            '[class*="post-body"]',
            "main",
        ]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 100:
                    return text[:800]  # 最大800文字

        # 見つからなければ <p> タグを集める
        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 30]
        return " ".join(paragraphs)[:800]

    except Exception as e:
        print(f"  [WARN] 本文取得失敗: {e}")
        return ""


# ─── Google News RSS から前日の記事を全件取得 ─────────────────────────────────
def fetch_articles() -> list[dict]:
    print(f"[RSS] 取得中: {GOOGLE_NEWS_RSS}")
    feed = feedparser.parse(GOOGLE_NEWS_RSS)

    articles = []
    for entry in feed.entries:
        pub = entry.get("published", "")
        if not is_yesterday(pub):
            continue  # 前日以外はスキップ

        articles.append({
            "title":   entry.get("title", "").strip(),
            "link":    entry.get("link", ""),
            "source":  entry.get("source", {}).get("title", "Google News"),
            "published": pub,
            "body":    "",
        })

    print(f"[OK] 前日の記事: {len(articles)} 件")

    # 各記事の本文を取得
    for i, a in enumerate(articles):
        print(f"  [{i+1}/{len(articles)}] 本文取得: {a['title'][:40]}...")
        a["body"] = fetch_article_body(a["link"])
        time.sleep(REQUEST_INTERVAL)

    return articles


def summarize_with_ollama(title: str, body: str) -> str:
    content = body if body else title

    prompt = f"""以下のニュース記事を、関西弁で初心者向けに解説してください。

条件：
- 関西弁（やわらかい口語）で書く
- 専門用語が出てきたら「〇〇（←△△のこと）」のように注釈をカッコ内に入れる
- IT・ビジネスの知識ゼロの人でも分かるように
- 「なんでこれが大事なん？」という視点を一言入れる
- 4〜5文でまとめる

タイトル: {title}
記事内容: {content}"""

    try:
        resp = requests.post(
            "http://localhost:11434/api/chat",  # Ollamaのローカルサーバー
            json={
                "model": "gemma4",
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,  # Falseにすると全文まとめて返ってくる
            },
            timeout=120,  # ローカルLLMはAPIより遅いので長めに設定
        )
        return resp.json()["message"]["content"].strip()
    except Exception as e:
        print(f"  [WARN] Ollama エラー: {e}")
        return body[:200] if body else "（要約に失敗しました）"


# ─── Gemini API で関西弁・初心者向け要約 ─────────────────────────────────────
def summarize_with_gemini(title: str, body: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return body[:200] if body else "（本文を取得できませんでした）"

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-flash-latest:generateContent?key={api_key}"
    )

    content = body if body else title

    prompt = f"""以下のニュース記事を、関西弁で初心者向けに解説してください。

条件：
- 関西弁（やわらかい口語）で書く
- 専門用語が出てきたら「〇〇（←△△のこと）」のように注釈をカッコ内に入れる
- IT・ビジネスの知識ゼロの人でも分かるように
- 「なんでこれが大事なん？」という視点を一言入れる
- 4〜5文でまとめる

タイトル: {title}
記事内容: {content}"""

    try:
        resp = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=20,
        )
        data = resp.json()
        if "candidates" not in data:
            error_msg = data.get("error", {}).get("message", str(data))
            print(f"  [WARN] Gemini API 異常レスポンス: {error_msg}")
            return f"（Gemini APIエラー: {error_msg}）"
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"  [WARN] Gemini API エラー: {e}")
        return f"（要約失敗: {e}）"


# ─── HTML 生成 ────────────────────────────────────────────────────────────────
def generate_html(articles: list[dict]) -> None:
    jst      = timezone(timedelta(hours=9))
    now      = datetime.now(jst)
    yesterday = (now - timedelta(days=1)).strftime("%Y年%m月%d日")
    ts_str    = now.strftime("%Y-%m-%d %H:%M JST")

    cards_html = ""
    for a in articles:
        ai_text = a.get("ollama_summary", "").replace("<", "&lt;").replace(">", "&gt;")
        original = a.get("body", "")[:200].replace("<", "&lt;").replace(">", "&gt;")
        cards_html += f"""<article class="card">
  <div class="meta">
    <span class="source">{a['source']}</span>
  </div>
  <h3><a href="{a['link']}" target="_blank" rel="noopener">{a['title']}</a></h3>
  <div class="badge">🤖 関西弁AI解説</div>
  <p class="ai-summary">{ai_text}</p>
  <details>
    <summary>元の記事を見る</summary>
    <p class="original">{original}…</p>
  </details>
</article>\n"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily News — {yesterday}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8; --green: #34d399;
    --font: 'Segoe UI', 'Hiragino Sans', sans-serif;
  }}
  body {{ font-family: var(--font); background: var(--bg); color: var(--text); line-height: 1.7; }}
  header {{
    background: linear-gradient(160deg, #1e3a5f 0%, #0f172a 100%);
    padding: 2.5rem 1rem 2rem; text-align: center;
    border-bottom: 1px solid var(--border);
  }}
  header h1 {{ font-size: 2rem; color: var(--accent); }}
  header p  {{ color: var(--muted); margin-top: .4rem; font-size: .95rem; }}
  .count {{ color: var(--green); font-size: .85rem; margin-top: .3rem; }}
  main {{ max-width: 860px; margin: 2.5rem auto; padding: 0 1rem 4rem; }}
  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.2rem 1.5rem; margin-bottom: 1rem;
    transition: border-color .15s, transform .15s;
  }}
  .card:hover {{ border-color: var(--accent); transform: translateY(-1px); }}
  .meta {{ display: flex; align-items: center; gap: .6rem; margin-bottom: .4rem; }}
  .source {{ font-size: .72rem; color: var(--accent); opacity: .8; text-transform: uppercase; letter-spacing: .05em; }}
  .card h3 {{ font-size: .97rem; margin-bottom: .6rem; font-weight: 600; }}
  .card h3 a {{ color: var(--text); text-decoration: none; }}
  .card h3 a:hover {{ color: var(--accent); }}
  .badge {{
    display: inline-block; font-size: .7rem; padding: .15rem .5rem;
    background: rgba(52,211,153,.15); color: var(--green);
    border: 1px solid rgba(52,211,153,.3); border-radius: 4px; margin-bottom: .6rem;
  }}
  .ai-summary {{ font-size: .93rem; line-height: 1.8; margin-bottom: .8rem; }}
  details summary {{
    font-size: .78rem; color: var(--muted); cursor: pointer; list-style: none;
    display: flex; align-items: center; gap: .3rem;
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
  <p>{yesterday}のニュース — ollama AIが関西弁で解説</p>
  <p class="count">全 {len(articles)} 件</p>
</header>
<main>
{cards_html}
</main>
<footer>Updated via GitHub Actions &nbsp;·&nbsp; {ts_str}</footer>
</body>
</html>"""

    Path("docs").mkdir(exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("[OK] docs/index.html 生成完了")


# ─── Telegram 通知 ────────────────────────────────────────────────────────────
def send_telegram(articles: list[dict], page_url: str) -> None:
    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    jst      = timezone(timedelta(hours=9))
    yesterday = (datetime.now(jst) - timedelta(days=1)).strftime("%Y/%m/%d")

    lines = [f"📰 *{yesterday} ニュースまとめ（全{len(articles)}件）*\n"]
    for a in articles[:5]:
        title = a["title"].replace("*", "\\*").replace("[", "\\[").replace("]", "\\]")
        lines.append(f"• [{title}]({a['link']})")

    if len(articles) > 5:
        lines.append(f"\n他 {len(articles) - 5} 件...")

    lines.append(f"\n🔗 [関西弁AI解説つき全記事を読む]({page_url})")

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

    print("=== Step 1: Google News から前日の記事を取得 ===")
    articles = fetch_articles()

    if not articles:
        print("[WARN] 前日の記事が見つかりませんでした。終了します。")
        exit(0)

    print(f"\n=== Step 2: Gemini で関西弁要約（{len(articles)} 件） ===")
    for i, a in enumerate(articles):
        print(f"  [{i+1}/{len(articles)}] {a['title'][:40]}...")
        a["ollama_summary"] = summarize_with_ollama(a["title"], a["body"])
        time.sleep(1)  # API レート制限対策

    print("\n=== Step 3: HTML 生成 ===")
    generate_html(articles)

    print("\n=== Step 4: Telegram 通知 ===")
    send_telegram(articles, page_url)

    print("\n=== 完了 ===")
