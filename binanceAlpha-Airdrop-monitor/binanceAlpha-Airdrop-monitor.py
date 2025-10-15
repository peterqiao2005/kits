#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
monitor_airdrops.py
每30分钟执行一次；如检测到 alpha123.uk 页面数据变更，在终端打印变更 diff，并通过 Lark 机器人推送。
改动点：
1) 使用单一会话先抓 HTML（设置 cookie），再抓 API；
2) 如遇 403/503，自动切换 cloudscraper 重试；
3) HTML 与 API 合并为一份快照，任一来源更新都触发告警；
4) 失败时打印更明确的来源错误，不改变原有监控/告警逻辑。
5) 仅在“检测到变化”时，追加输出 & 推送 “Today 的当前完整列表” 以便人读。
"""

import hashlib
import json
import os
import sys
import time
import difflib
from typing import List, Tuple

import requests
from lxml import html as lxml_html

# === 可调参数 ===
URL_API = "https://alpha123.uk/api/data?fresh=1"
URL_PAGE = "https://alpha123.uk/"
STATE_DIR = os.environ.get("AIRMON_STATE_DIR", "/var/tmp")
STATE_PATH = os.path.join(STATE_DIR, "monitor_airdrops.state.json")
TIMEOUT = (10, 25)  # (connect, read)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
BASE_HEADERS_JSON = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://alpha123.uk/",
    "Origin": "https://alpha123.uk",
    "Accept-Language": "en-US,en;q=0.9",
}
BASE_HEADERS_HTML = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://alpha123.uk/",
    "Accept-Language": "en-US,en;q=0.9",
}

# === Lark Webhook ===
SEND_URL = "https://open.larksuite.com/open-apis/bot/v2/hook/7a95d2ce-fc66-4d7c-bb03-5af5509cc4ad"

# 你提供的函数，原样保留
def send_wechat_message(content, send_url):
    headers = {"Content-Type": "application/json"}
    data = {
        "msg_type": "text",
        "content": {
            "text": "【告警】 质押 \n" + content
        }
    }
    response = requests.post(send_url, headers=headers, data=json.dumps(data))
    print("状态码:", response.status_code)
    print("返回内容:", response.text)


# ========== 抓取辅助 ==========
try:
    import cloudscraper  # noqa: F401
    HAVE_CLOUDSCRAPER = True
except Exception:
    cloudscraper = None  # type: ignore
    HAVE_CLOUDSCRAPER = False


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_lines(lines: List[str]) -> List[str]:
    norm = []
    for s in lines:
        s = " ".join(s.split())
        s = s.replace("\xa0", " ").strip()
        norm.append(s)
    return norm


def _make_browser_session(prefer_cloud: bool = False):
    """
    创建“更像浏览器”的会话。优先 requests；必要时使用 cloudscraper。
    """
    if prefer_cloud and HAVE_CLOUDSCRAPER:
        sess = cloudscraper.create_scraper()  # type: ignore
    else:
        sess = requests.Session()
    # 统一加一些常见头
    sess.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    return sess


def _get_with_fallback(sess, url: str, headers: dict):
    """
    先用当前会话请求；若 403/503，再用 cloudscraper 重试一次。
    返回 (response, used_scraper: bool)
    """
    try:
        r = sess.get(url, headers=headers, timeout=TIMEOUT)
        if r.status_code not in (403, 503):
            r.raise_for_status()
            return r, False
    except requests.RequestException:
        # 如果是其它网络错误，后面也尝试 cloudscraper
        pass

    # Fallback 到 cloudscraper（若可用）
    if HAVE_CLOUDSCRAPER:
        try:
            sc = cloudscraper.create_scraper()  # type: ignore
            # 让 scraper 继承 cookies（有时 HTML 先拿到的 cf cookie 能帮助第二次请求）
            try:
                sc.cookies.update(sess.cookies)
            except Exception:
                pass
            r2 = sc.get(url, headers=headers, timeout=TIMEOUT)
            r2.raise_for_status()
            return r2, True
        except Exception as ee:
            raise ee
    else:
        # 没安装 cloudscraper，直接抛出原错误（或 403）
        r.raise_for_status()
        return r, False  # noqa: unreachable


def snapshot_from_html(sess) -> Tuple[List[str], dict]:
    """
    解析首页 HTML：提取两张表格所有行，按列拼接。
    """
    r, used_scraper = _get_with_fallback(sess, URL_PAGE, BASE_HEADERS_HTML)
    doc = lxml_html.fromstring(r.content)

    lines: List[str] = []

    def extract_table(table_id: str, section: str):
        for tr in doc.xpath(f'//table[@id="{table_id}"]/tbody/tr'):
            tds = tr.xpath("./td")
            if not tds:
                continue

            token_symbol = (
                "".join(tds[0].xpath('.//div[@class="token-symbol"]/text()')).strip() or "-"
            )
            token_fullname = (
                "".join(tds[0].xpath('.//div[@class="token-fullname"]/text()')).strip() or "-"
            )

            points = "".join(
                tds[1].xpath(".//span[contains(@class,'points-badge')]/text()")
            ).strip() or "-"

            amount_span = tds[2].xpath(".//span[contains(@class,'points-badge')]/text()")
            amount = amount_span[0].strip() if amount_span else "-"

            dex_value = "".join(
                tds[2].xpath(".//div[contains(@class,'dex-price-value')]/text()")
            ).strip() or "-"
            exch_value = "".join(
                tds[2].xpath(".//div[contains(@class,'exchange-price-value')]/text()")
            ).strip() or "-"

            time_text = "".join(
                tds[3].xpath(".//div[contains(@class,'time-cell')]/text()")
            ).strip() or "-"

            is_grab = "⚡" if tds[3].xpath(".//i[contains(@class,'bi-lightning-fill')]") else ""
            is_done = "✔" if tds[3].xpath(".//i[contains(@class,'bi-check-circle-fill')]") else ""

            line = " | ".join(
                [
                    section,
                    token_symbol,
                    token_fullname,
                    points,
                    amount,
                    dex_value,
                    exch_value,
                    time_text,
                    is_grab,
                    is_done,
                ]
            )
            lines.append(line)

    extract_table("today-airdrops", "today")
    extract_table("upcoming-airdrops", "upcoming")

    lines = sorted(_normalize_lines(lines))
    meta = {"source": "html" + ("+cloudscraper" if used_scraper else ""), "count": len(lines)}
    return lines, meta


def snapshot_from_api(sess) -> Tuple[List[str], dict]:
    """
    调 /api/data?fresh=1，生成“和表格等价”的快照行。
    每条：section | token | name | points | amount | date | time | phase | status | price | dex_price
    """
    r, used_scraper = _get_with_fallback(sess, URL_API, BASE_HEADERS_JSON)
    data = r.json()

    if not isinstance(data, dict) or "airdrops" not in data:
        raise ValueError("API payload unexpected")

    lines = []
    for ad in data["airdrops"]:
        section = "today_or_upcoming"
        token = str(ad.get("token") or "-").strip()
        name = str(ad.get("name") or "-").strip()
        points = str(ad.get("points") or "-").strip()
        amount = str(ad.get("amount") or "-").strip()
        date = str(ad.get("date") or "-").strip()
        tm = str(ad.get("time") or "-").strip()
        phase = str(ad.get("phase") or "-").strip()
        price = str(ad.get("price") or "-").strip()
        dex_price = str(ad.get("dex_price") or "-").strip()
        status = str(ad.get("status") or "-").strip()
        line = " | ".join(
            [section, token, name, points, amount, date, tm, phase, status, price, dex_price]
        )
        lines.append(line)

    lines = sorted(_normalize_lines(lines))
    meta = {"source": "api" + ("+cloudscraper" if used_scraper else ""), "count": len(lines)}
    return lines, meta


def combined_snapshot() -> Tuple[List[str], dict]:
    """
    同一会话先抓 HTML（拿 cookie），再抓 API；若某一端失败不致命。
    最终结果为二者并集（去重）。
    """
    sess = _make_browser_session(prefer_cloud=False)

    html_lines: List[str] = []
    api_lines: List[str] = []
    meta_html: dict = {}
    meta_api: dict = {}
    err_html = err_api = None

    # 先 HTML
    try:
        html_lines, meta_html = snapshot_from_html(sess)
    except Exception as e:
        err_html = e

    # 再 API（带上 HTML 获得的 cookie）
    try:
        api_lines, meta_api = snapshot_from_api(sess)
    except Exception as e:
        err_api = e

    if not html_lines and not api_lines:
        # 两个都失败，抛出更有信息量的错误
        raise err_api or err_html or RuntimeError("both sources empty")

    merged = sorted(set(html_lines) | set(api_lines))
    meta = {
        "source": "+".join([s for s in [meta_html.get("source"), meta_api.get("source")] if s]),
        "count": len(merged),
        "html_count": len(html_lines),
        "api_count": len(api_lines),
        "html_error": str(err_html) if err_html else "",
        "api_error": str(err_api) if err_api else "",
    }
    return merged, meta


# -------- 新增：仅在“有变化”时，取 Today 表格并转成人读友好的文本 --------
def build_today_overview_text() -> str:
    """
    抓取 Today 概览：
    1) 先尝试解析首页 HTML；
    2) 若 HTML 为空，则回退到 API：按北京时间(UTC+8)的 `date`==今天 过滤；
    3) 统一格式化为人类可读文本。
    仅在本函数内做逻辑，不影响其它监控/告警部分。
    """
    from datetime import datetime, timezone, timedelta

    # -------- 优先：HTML 解析 --------
    sess = _make_browser_session(prefer_cloud=False)
    try:
        r, _ = _get_with_fallback(sess, URL_PAGE, BASE_HEADERS_HTML)
        doc = lxml_html.fromstring(r.content)
        rows = doc.xpath('//table[@id="today-airdrops"]/tbody/tr')

        out_lines = []
        out_lines.append("TOKEN  | PROJECT         | POINTS | AMOUNT | TIME")
        out_lines.append("-------+-----------------+--------+--------+-------------------------")

        data_found = False
        for tr in rows:
            tds = tr.xpath("./td")
            if not tds:
                continue
            # “No data available” 行（单元格合并）直接跳过，不计为数据
            if len(tds) == 1:
                text_all = " ".join("".join(tds[0].xpath(".//text()")).split()).lower()
                if "no data available" in text_all:
                    continue
                # 其他异常结构也忽略
                continue
            if len(tds) < 4:
                continue

            sym  = ("".join(tds[0].xpath('.//div[@class="token-symbol"]/text()')).strip() or "-")
            name = ("".join(tds[0].xpath('.//div[@class="token-fullname"]/text()')).strip() or "-")
            pts  = "".join(tds[1].xpath('.//span[contains(@class,"points-badge")]/text()')).strip() or "-"
            amtN = tds[2].xpath('.//span[contains(@class,"points-badge")]/text()')
            amt  = (amtN[0].strip() if amtN else "-")
            time_text = "".join(tds[3].xpath('.//div[contains(@class,"time-cell")]/text()')).strip() or "-"

            out_lines.append(f"{sym:<6} | {name:<15} | {pts:>6} | {amt:>6} | {time_text}")

            dex = "".join(tds[2].xpath('.//div[contains(@class,"dex-price-value")]/text()')).strip()
            exc = "".join(tds[2].xpath('.//div[contains(@class,"exchange-price-value")]/text()')).strip()
            price_bits = [p for p in (dex, exc) if p]
            if price_bits:
                out_lines.append("       |                 |        |        | " + " / ".join(price_bits))

            data_found = True

        if data_found:
            return "\n".join(out_lines)

    except Exception as _e:
        # HTML 失败就走 API 回退；不在这里抛
        pass

    # -------- 回退：通过 API 组装 Today （UTC+8）--------
    try:
        r2, _ = _get_with_fallback(sess, URL_API, BASE_HEADERS_JSON)
        data = r2.json()
        airdrops = data.get("airdrops", [])
    except Exception as e:
        return f"(Today overview failed: {e.__class__.__name__})"

    # 以北京时间判定“今天”
    tz8 = timezone(timedelta(hours=8))
    today_str = datetime.now(tz8).strftime("%Y-%m-%d")

    rows = []
    for ad in airdrops:
        date = (ad.get("date") or "").strip()
        if date != today_str:
            continue
        token = (ad.get("token") or "-").strip()
        name  = (ad.get("name") or "-").strip()
        points = str(ad.get("points") or "-").strip()
        amount = str(ad.get("amount") or "-").strip()
        tm     = (ad.get("time") or "-").strip()
        phase  = str(ad.get("phase") or "-").strip()
        typ    = (ad.get("type") or "").strip().lower()
        price  = ad.get("price")
        dex_price = ad.get("dex_price")

        # 展示用时间字符串
        time_display = tm if tm else "TBA"
        if phase == "2":
            time_display += " (Phase 2)"
        if typ == "tge":
            time_display += " (TGE)"

        # 估值（若有）
        price_line = ""
        try:
            amt_float = float(amount)
        except Exception:
            amt_float = None

        price_bits = []
        if amt_float is not None and isinstance(dex_price, (int, float)) and dex_price > 0:
            price_bits.append(f"DEX ${round(dex_price * amt_float, 1)}")
        if amt_float is not None and isinstance(price, (int, float)) and price > 0:
            price_bits.append(f"EX  ${round(price * amt_float, 1)}")

        rows.append({
            "token": token,
            "name": name,
            "points": points,
            "amount": amount,
            "time_display": time_display,
            "price_line": " / ".join(price_bits) if price_bits else "",
            # 排序键：无时间的放后面
            "sort_key": (tm if tm else "99:99")
        })

    if not rows:
        return "No data available"

    rows.sort(key=lambda x: x["sort_key"])

    out_lines = []
    out_lines.append("TOKEN  | PROJECT         | POINTS | AMOUNT | TIME")
    out_lines.append("-------+-----------------+--------+--------+-------------------------")
    for r in rows:
        out_lines.append(f"{r['token']:<6} | {r['name']:<15} | {r['points']:>6} | {r['amount']:>6} | {r['time_display']}")
        if r["price_line"]:
            out_lines.append("       |                 |        |        | " + r["price_line"])

    return "\n".join(out_lines)

def load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main() -> int:
    try:
        lines, meta = combined_snapshot()
        snapshot_text = "\n".join(lines) + "\n"
        snapshot_hash = _sha256(snapshot_text.encode("utf-8"))
        now = int(time.time())

        state = load_state()
        prev_hash = state.get("hash")
        prev_text = state.get("text", "")

        if prev_hash == snapshot_hash:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] No change detected (source={meta['source']}, rows={meta['count']}, html={meta.get('html_count',0)}, api={meta.get('api_count',0)})")
            return 0

        # 有变化：打印统一 diff，并推送到 Lark；随后追加 Today 概览
        prev_lines = prev_text.splitlines(keepends=False)
        new_lines = snapshot_text.splitlines(keepends=False)
        diff_iter = difflib.unified_diff(
            prev_lines,
            new_lines,
            fromfile="previous",
            tofile="current",
            lineterm="",
        )

        diff_lines_collected = []
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Detected update (source={meta['source']}, rows={meta['count']}, html={meta.get('html_count',0)}, api={meta.get('api_count',0)})")
        for line in diff_iter:
            diff_lines_collected.append(line)
            print(line)

        # 追加 Today 概览文本
        today_overview = build_today_overview_text()
        print("\n=== Today's Airdrops (current) ===")
        print(today_overview)

        # 发送到 Lark
        if not diff_lines_collected:
            # 第一次建立基线，也把当前 Today 发过去
            content = "(no previous snapshot — baseline stored)\n\n=== Today's Airdrops (current) ===\n" + today_overview
            send_wechat_message(content, SEND_URL)
        else:
            diff_text = "\n".join(diff_lines_collected)
            content = diff_text + "\n\n=== Today's Airdrops (current) ===\n" + today_overview
            send_wechat_message(content, SEND_URL)

        # 落盘
        state = {
            "hash": snapshot_hash,
            "text": snapshot_text,
            "meta": {"updated_at": now, **meta},
        }
        save_state(state)
        return 0

    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: snapshot failed: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

root@ln1:~/workspace/kits# 