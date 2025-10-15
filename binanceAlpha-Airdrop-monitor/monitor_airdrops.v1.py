#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
monitor_airdrops.py
每30分钟执行一次；如检测到 alpha123.uk 页面数据变更，在终端打印变更 diff，并通过 Lark 机器人推送。
改动点：同时抓 API 和 HTML，合并为快照，任一来源变化都触发告警；请求头增加 no-cache。
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

URL_API = "https://alpha123.uk/api/data?fresh=1"
URL_PAGE = "https://alpha123.uk/"
STATE_DIR = os.environ.get("AIRMON_STATE_DIR", "/var/tmp")
STATE_PATH = os.path.join(STATE_DIR, "monitor_airdrops.state.json")
TIMEOUT = (10, 20)  # (connect, read)
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
BASE_HEADERS_JSON = {
    "User-Agent": UA,
    "Accept": "application/json",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}
BASE_HEADERS_HTML = {
    "User-Agent": UA,
    "Accept": "text/html",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
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


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_lines(lines: List[str]) -> List[str]:
    norm = []
    for s in lines:
        s = " ".join(s.split())
        s = s.replace("\xa0", " ").strip()
        norm.append(s)
    return norm


def snapshot_from_api() -> Tuple[List[str], dict]:
    """
    调 /api/data?fresh=1，生成“和表格等价”的快照行。
    每条：section | token | name | points | amount | date | time | phase | status | price | dex_price
    """
    r = requests.get(URL_API, headers=BASE_HEADERS_JSON, timeout=TIMEOUT)
    r.raise_for_status()
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
    meta = {"source": "api", "count": len(lines)}
    return lines, meta


def snapshot_from_html() -> Tuple[List[str], dict]:
    """
    解析首页 HTML：提取两张表格所有行，按列拼接。
    """
    r = requests.get(URL_PAGE, headers=BASE_HEADERS_HTML, timeout=TIMEOUT)
    r.raise_for_status()
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
    meta = {"source": "html", "count": len(lines)}
    return lines, meta


def combined_snapshot() -> Tuple[List[str], dict]:
    """
    同时取 HTML 和 API；合并（并集去重）后作为最终快照。
    任一来源的新增/变更都会引发哈希变化。
    """
    html_lines, api_lines = [], []
    meta_html, meta_api = {}, {}
    err_html = err_api = None

    try:
        html_lines, meta_html = snapshot_from_html()
    except Exception as e:
        err_html = e

    try:
        api_lines, meta_api = snapshot_from_api()
    except Exception as e:
        err_api = e

    if not html_lines and not api_lines:
        # 两个都失败，抛出更有价值的异常
        raise err_api or err_html or RuntimeError("both sources empty")

    merged = sorted(set(html_lines) | set(api_lines))
    meta = {
        "source": "+".join([s for s in [meta_html.get("source"), meta_api.get("source")] if s]),
        "count": len(merged),
        "html_count": len(html_lines),
        "api_count": len(api_lines),
    }
    return merged, meta


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

        # 有变化：打印统一 diff，并推送到 Lark
        prev_lines = prev_text.splitlines(keepends=False)
        new_lines = snapshot_text.splitlines(keepends=False)
        diff_iter = difflib.unified_diff(
            prev_lines,
            new_lines,
            fromfile="previous",
            tofile="current",
            lineterm="",
            n=0
        )

        diff_lines_collected = []
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Detected update (source={meta['source']}, rows={meta['count']}, html={meta.get('html_count',0)}, api={meta.get('api_count',0)})")
        for line in diff_iter:
            diff_lines_collected.append(line)
            print(line)

        if not diff_lines_collected:
            print("(no previous snapshot — baseline stored)")
        else:
            diff_text = "\n".join(diff_lines_collected)
            send_wechat_message(diff_text, SEND_URL)

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

