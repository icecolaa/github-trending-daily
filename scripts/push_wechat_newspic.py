# -*- coding: utf-8 -*-
"""
把当天的小红书竖版图（pic/<日期>/xhs/*.png）推到公众号「图片消息」草稿箱（贴图）。

用法:
  python scripts/push_wechat_newspic.py                    # 推当天
  python scripts/push_wechat_newspic.py --date 20261105    # 推指定日期
  python scripts/push_wechat_newspic.py --dry-run          # 只校验、不真推
  python scripts/push_wechat_newspic.py --force            # 同日已推过也再推一份

行为:
  1. 从 pic/<日期>/xhs/ 取 01~06 六张 PNG（按文件名排序，最多 20 张）
  2. 逐张上传为「永久图片素材」（material/add_material?type=image）拿 media_id
  3. 调 draft/add 建 article_type=newspic 的草稿，图片按顺序排好
  4. 把草稿 media_id 与图片清单记到 .build/wechat_drafts.json，防止同日重复推

凭证: ~/.workbuddy/wechat-publisher.env 里的 WECHAT_APP_ID / WECHAT_APP_SECRET
      （或同名环境变量）。不打印、不落盘。

退出码: 0 成功 / 1 失败 / 2 缺凭证或缺图 / 3 当日已推过（跳过）
"""

import argparse
import json
import mimetypes
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.weixin.qq.com/cgi-bin"
RECORD = ROOT / ".build" / "wechat_drafts.json"
MAX_IMAGES = 20
TITLE_MAX = 64

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ---------------------------------------------------------------- 凭证

def credentials():
    envp = Path(os.path.expanduser("~/.workbuddy/wechat-publisher.env"))
    kv = {}
    if envp.exists():
        for line in envp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip().strip('"').strip("'")
    app_id = kv.get("WECHAT_APP_ID") or os.environ.get("WECHAT_APP_ID")
    app_secret = kv.get("WECHAT_APP_SECRET") or os.environ.get("WECHAT_APP_SECRET")
    if not app_id or not app_secret:
        raise SystemExit(f"✗ 缺少公众号凭证，检查 {envp} 里的 WECHAT_APP_ID / WECHAT_APP_SECRET")
    return app_id, app_secret


def get_token(app_id, app_secret):
    r = requests.get(f"{API}/token", params={
        "grant_type": "client_credential", "appid": app_id, "secret": app_secret}, timeout=30)
    d = r.json()
    if d.get("errcode"):
        raise RuntimeError(f"获取 access_token 失败 [{d['errcode']}] {d.get('errmsg')}")
    return d["access_token"]


def explain(errcode, errmsg):
    hints = {
        40001: "access_token 失效，重试一次通常即可",
        40125: "AppSecret 不对，检查 ~/.workbuddy/wechat-publisher.env",
        40164: "本机出口 IP 不在公众号 IP 白名单里，去「设置与开发 → 基本配置 → IP白名单」加一下",
        40005: "文件类型不支持，公众号只认 bmp/png/jpeg/jpg/gif",
        40006: "图片超过 10MB 或尺寸不合规",
        40009: "图片大小为 0",
        45009: "接口调用频次超限，等一会儿再试",
        48001: "该接口未授权，确认公众号类型是否支持图片消息草稿",
        53404: "账号已被限制，先看公众号后台的通知",
    }
    h = hints.get(errcode)
    return f"[{errcode}] {errmsg}" + (f" —— {h}" if h else "")


# ---------------------------------------------------------------- 文案

def read_note(xhs_dir):
    """从 发布文案.md 里取标题与描述；缺失时退回 data.json。"""
    title, desc, tags = "", "", ""
    note = xhs_dir / "发布文案.md"
    if note.exists():
        txt = note.read_text(encoding="utf-8")
        lines = [l.rstrip() for l in txt.splitlines()]
        for l in lines:
            if l.startswith("# "):
                title = l[2:].strip()
                break
        body = [l for l in lines if l and not l.startswith("#") and not l.startswith("- ")
                and not l.startswith("---")]
        paras = [l for l in body if not l.startswith(("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣",
                                                     "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"))]
        if paras:
            desc = paras[0].strip()
        for l in lines:
            if l.startswith("#") and not l.startswith("# "):
                tags = l.strip()
                break
    data_json = xhs_dir / "data.json"
    if data_json.exists():
        d = json.loads(data_json.read_text(encoding="utf-8"))
        title = title or d.get("note_title") or d.get("headline") or ""
        desc = desc or d.get("overview") or ""
        tags = tags or " ".join(d.get("hashtags") or [])
    return title.strip(), desc.strip(), tags.strip()


def build_content(desc, tags, n_images):
    parts = [desc] if desc else []
    parts.append(f"共 {n_images} 张竖版图，滑动看完今天完整的 GitHub 飙升榜。")
    if tags:
        parts.append(tags)
    return "\n".join(parts)


# ---------------------------------------------------------------- 接口

def upload_image(token, path):
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    with path.open("rb") as f:
        r = requests.post(f"{API}/material/add_material",
                          params={"access_token": token, "type": "image"},
                          files={"media": (path.name, f, mime)}, timeout=90)
    d = r.json()
    if d.get("errcode"):
        raise RuntimeError(f"上传 {path.name} 失败 {explain(d['errcode'], d.get('errmsg'))}")
    mid = d.get("media_id")
    if not mid:
        raise RuntimeError(f"上传 {path.name} 未返回 media_id: {d}")
    return mid, d.get("url", "")


def create_newspic_draft(token, title, content, media_ids, thumb_id=None):
    article = {
        "article_type": "newspic",
        "title": title[:TITLE_MAX],
        "content": content,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
        "image_info": {"image_list": [{"image_media_id": m} for m in media_ids]},
    }
    # 草稿箱列表用 thumb 做缩略封面；不给的话会拿首图瞎裁，封面常常缺字
    if thumb_id:
        article["thumb_media_id"] = thumb_id
    body = json.dumps({"articles": [article]}, ensure_ascii=False).encode("utf-8")
    r = requests.post(f"{API}/draft/add", params={"access_token": token},
                      data=body, headers={"Content-Type": "application/json"}, timeout=60)
    d = r.json()
    if d.get("errcode"):
        raise RuntimeError(f"建草稿失败 {explain(d['errcode'], d.get('errmsg'))}")
    return d.get("media_id")


# ---------------------------------------------------------------- 记录

def load_record():
    if RECORD.exists():
        try:
            return json.loads(RECORD.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_record(rec):
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD，默认今天")
    ap.add_argument("--dir", help="图片目录，默认 pic/<date>/xhs")
    ap.add_argument("--title")
    ap.add_argument("--desc")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="同日已推过也再推一份")
    ap.add_argument("--no-cover", action="store_true",
                    help="不插入 wechat/公众号封面.png 作为首图")
    args = ap.parse_args()

    date = args.date or datetime.now().strftime("%Y%m%d")
    xhs = Path(args.dir) if args.dir else ROOT / "pic" / date / "xhs"
    if not xhs.exists():
        print(f"✗ 找不到图片目录 {xhs}")
        return 2

    images = sorted([p for p in xhs.glob("*.png") if re.match(r"^\d{2}-", p.name)])
    if not images:
        print(f"✗ {xhs} 下没有 01-xx.png 这类卡片")
        return 2

    # 安全封面放首位：草稿箱列表拿首图当缩略图并居中裁剪，竖版卡片的边字会被切
    cover = xhs.parent / "wechat" / "公众号封面.png"
    pages = list(images)
    if cover.exists() and not args.no_cover:
        pages = [cover] + pages
    pages = pages[:MAX_IMAGES]

    title, desc, tags = read_note(xhs)
    title = args.title or title or f"GitHub 飙升榜 {date}"
    desc = args.desc or desc
    content = build_content(desc, tags, len(images))

    print(f"== 贴图草稿 · {date} · {xhs}")
    print(f"   标题：{title}")
    print(f"   描述：{content.splitlines()[0][:60]}…（共 {len(content)} 字）")
    print(f"   图片：{len(pages)} 张"
          f"{'（含安全封面 + ' + str(len(images)) + ' 张竖版图）' if pages is not images and pages[0] is cover else ''}")
    for p in pages:
        print(f"     - {p.name}  {p.stat().st_size // 1024} KB")

    rec = load_record()
    prev = rec.get(date)
    if prev and not args.force and not args.dry_run:
        print(f"· {date} 于 {prev.get('pushed_at')} 已推过草稿 media_id={prev.get('media_id','')[:16]}…，跳过（--force 可再推）")
        return 3

    if args.dry_run:
        print("· [dry-run] 校验通过，未调用公众号接口")
        return 0

    app_id, app_secret = credentials()
    token = get_token(app_id, app_secret)
    print("✓ access_token 获取成功")

    media_ids, urls = [], []
    for i, p in enumerate(pages, 1):
        mid, url = upload_image(token, p)
        media_ids.append(mid)
        urls.append(url)
        print(f"   [{i}/{len(pages)}] ✓ {p.name} → media_id={mid[:20]}…")
        time.sleep(0.3)

    draft_id = create_newspic_draft(token, title, content, media_ids, thumb_id=media_ids[0])
    if not draft_id:
        print("✗ 建草稿未返回 media_id")
        return 1

    rec[date] = {
        "media_id": draft_id,
        "title": title,
        "image_count": len(pages),
        "image_files": [p.name for p in pages],
        "image_media_ids": media_ids,
        "pushed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_record(rec)
    print(f"✓ 草稿已建：media_id={draft_id}")
    print("  到公众号后台「内容与互动 → 草稿箱 → 图片」里就能看到，确认后手动发布")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"✗ {e}")
        sys.exit(1)
