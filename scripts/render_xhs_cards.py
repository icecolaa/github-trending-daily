# -*- coding: utf-8 -*-
"""
GitHub 飙升榜 -> 小红书竖版图文卡片

把结构化榜单数据渲染成 1080x1440 的 PNG 组图（封面 / 今日看点 / 榜单分页 / 结尾），
并产出可直接复制的小红书笔记文案与一个预览页。

用法:
  python scripts/render_xhs_cards.py --data articles/src/xxx.json
  python scripts/render_xhs_cards.py --from-md articles/src/xxx.md
  python scripts/render_xhs_cards.py --data xxx.json --theme dark --out pic/20261104/xhs

可选参数:
  --out      输出目录，默认 pic/<date>/xhs
  --theme    light(默认) / dark
  --per-page 每张榜单卡放几个项目，默认 4
  --chrome   手动指定 Chrome/Edge 可执行文件
  --no-shot  只生成 HTML，不截图（调试用）

数据来源约定见「云端订阅-图文版提示词.txt」中的 XHS_DATA 契约。
"""

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W, H = 1080, 1440

# ---------------------------------------------------------------- CSS

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1440px;overflow:hidden}
body{
  font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif;
  background:var(--bg);color:var(--ink);position:relative;
  -webkit-font-smoothing:antialiased;
}
.bg-grid{
  position:absolute;inset:0;pointer-events:none;
  background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);
  background-size:54px 54px;mask-image:linear-gradient(180deg,rgba(0,0,0,.9),rgba(0,0,0,.15));
}
.glow{position:absolute;border-radius:50%;filter:blur(90px);pointer-events:none}
.g1{width:620px;height:620px;top:-260px;right:-200px;background:var(--glow1);opacity:.55}
.g2{width:520px;height:520px;bottom:-260px;left:-220px;background:var(--glow2);opacity:.45}
.wrap{position:relative;z-index:2;width:100%;height:100%;padding:64px 72px 54px;display:flex;flex-direction:column}
/* 正文区独立成 flex 列：超出时由 FIT_JS 缩放，避免被画布直接裁掉 */
.main{flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden}
.inner{flex:1;display:flex;flex-direction:column}
.hd{display:flex;justify-content:space-between;align-items:center;font-size:22px;letter-spacing:2px;font-weight:700}
.hd .brand{color:var(--accent);display:flex;align-items:center;gap:12px}
.hd .dot{width:12px;height:12px;border-radius:50%;background:var(--hot);display:inline-block}
.hd .date{color:var(--muted);font-weight:600;letter-spacing:1px}
.ft{margin-top:auto;display:flex;justify-content:space-between;align-items:center;
   font-size:20px;color:var(--muted);border-top:1px solid var(--line);padding-top:22px}
.ft .pg{font-weight:800;color:var(--ink);letter-spacing:3px}
.big-num{position:absolute;right:34px;bottom:56px;font-size:420px;font-weight:900;
   line-height:1;color:var(--ghost);letter-spacing:-24px;pointer-events:none;z-index:1}
.pill{display:inline-block;padding:10px 20px;border-radius:999px;font-size:20px;font-weight:700;
   background:var(--pill);color:var(--accent);border:1px solid var(--line)}
.hot{color:var(--hot)}
.accent{color:var(--accent)}
.muted{color:var(--muted)}
.mono{font-family:"Consolas","SFMono-Regular",monospace;font-variant-numeric:tabular-nums}

/* 封面 */
/* 封面：正文再内缩一层，保证文字都落在中间 ~78% 的安全区里。
   公众号「贴图」草稿箱用第一张图做缩略封面，边缘会被裁，贴边的字会丢掉。 */
.cover-body{flex:1;display:flex;flex-direction:column;padding:0 58px}
.cover-title{font-size:90px;font-weight:900;line-height:1.16;letter-spacing:-2px;margin-top:84px}
.cover-title .num{font-size:114px;background:linear-gradient(100deg,var(--hot),var(--hot2));
   -webkit-background-clip:text;background-clip:text;color:transparent}
.cover-sub{font-size:54px;font-weight:900;letter-spacing:-1px;margin-top:10px}
.cover-kicker{font-size:26px;color:var(--muted);margin-top:26px;line-height:1.6}
.cover-pills{display:flex;gap:12px;flex-wrap:wrap;margin-top:42px}
.cover-stats{display:flex;gap:0;margin-top:auto;border-top:1px solid var(--line);padding-top:30px}
.cover-stats .s{flex:1;border-right:1px solid var(--line);padding-left:22px}
.cover-stats .s:first-child{padding-left:0}
.cover-stats .s:last-child{border-right:0}
.cover-stats .v{font-size:44px;font-weight:900;letter-spacing:-1px}
.cover-stats .l{font-size:19px;color:var(--muted);margin-top:6px}

/* 看点 */
.sec-title{font-size:66px;font-weight:900;letter-spacing:-2px;margin-top:56px}
.sec-desc{font-size:22px;color:var(--muted);margin-top:12px}
.overview{font-size:30px;line-height:1.72;margin-top:34px;font-weight:600}
.trends{margin-top:40px;display:flex;flex-direction:column;gap:16px}
.trend{display:flex;align-items:center;gap:26px;background:var(--card);
   border:1px solid var(--line);border-radius:24px;padding:24px 30px;box-shadow:var(--shadow)}
.trend .n{font-size:44px;font-weight:900;color:var(--hot);min-width:74px}
.trend .t{font-size:31px;font-weight:700;line-height:1.4}
.bars{margin-top:32px;background:var(--card);border:1px solid var(--line);
   border-radius:24px;padding:24px 30px 20px;box-shadow:var(--shadow)}
.bars h3{font-size:23px;font-weight:900;margin-bottom:20px;letter-spacing:1px}
.bar{display:flex;align-items:center;gap:16px;margin:15px 0;font-size:20px}
.bar .bn{width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:700}
.bar .track{flex:1;height:15px;background:var(--pill);border-radius:99px;overflow:hidden}
.bar .track i{display:block;height:100%;border-radius:99px;
   background:linear-gradient(90deg,var(--hot),var(--hot2))}
.bar .bv{width:120px;text-align:right;font-weight:900;color:var(--hot)}
.stat-row{display:flex;gap:18px;margin-top:auto;margin-bottom:8px}
.stat{flex:1;background:var(--card);border:1px solid var(--line);border-radius:22px;padding:26px 24px;text-align:center}
.stat .v{font-size:46px;font-weight:900}
.stat .l{font-size:19px;color:var(--muted);margin-top:8px}
.note{font-size:19px;color:var(--muted);line-height:1.6;margin-top:20px}

/* 榜单 */
.rank-head{display:flex;align-items:flex-end;justify-content:space-between;margin-top:44px}
.rank-head .t{font-size:68px;font-weight:900;letter-spacing:-2px}
.rank-head .s{font-size:21px;color:var(--muted);padding-bottom:12px}
.list{margin-top:28px;display:flex;flex-direction:column;gap:18px}
.row{position:relative;background:var(--card);border:1px solid var(--line);border-radius:26px;
   padding:26px 30px 24px 116px;min-height:242px;box-shadow:var(--shadow)}
.row .rk{position:absolute;left:26px;top:26px;font-size:66px;font-weight:900;
   color:var(--ghost2);line-height:1;letter-spacing:-4px}
.row .top{display:flex;justify-content:space-between;align-items:flex-start;gap:20px}
.repo-box{flex:1;min-width:0;line-height:1.12}
.owner-line{font-size:19px;font-weight:700;color:var(--muted);margin-bottom:8px;letter-spacing:.5px;
   white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.repo-name{font-weight:900;letter-spacing:-1px;white-space:nowrap;line-height:1.1}
.row .delta{font-size:52px;font-weight:900;color:var(--hot);white-space:nowrap;letter-spacing:-2px}
.row .delta small{font-size:22px;color:var(--muted);font-weight:700;margin-left:6px}
.row .meta{display:flex;gap:12px;align-items:center;margin-top:14px}
.row .tag{font-size:19px;font-weight:700;color:var(--accent);background:var(--pill);
   border:1px solid var(--line);border-radius:999px;padding:5px 16px}
.row .total{font-size:20px;color:var(--muted)}
.row .desc{font-size:25px;line-height:1.5;margin-top:16px;color:var(--ink);font-weight:600}
.fill-note{margin-top:20px;background:var(--pill);border:1px dashed var(--line);
   border-radius:22px;padding:20px 30px;font-size:21px;line-height:1.6;color:var(--muted)}
.full{margin-top:22px;background:var(--card);border:1px solid var(--line);
   border-radius:24px;padding:22px 30px;box-shadow:var(--shadow)}
.full h3{font-size:24px;font-weight:900;margin-bottom:14px;letter-spacing:1px}
.full .fr{display:flex;justify-content:space-between;align-items:center;
   font-size:21px;padding:7px 0;border-bottom:1px solid var(--line);color:var(--ink)}
.full .fr:last-child{border-bottom:0}
.full .fr .n{color:var(--muted);width:44px;font-weight:800}
.full .fr .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding-right:16px}
.full .fr .d{color:var(--hot);font-weight:800}

/* 结尾 */
.end-title{font-size:88px;font-weight:900;letter-spacing:-3px;margin-top:130px;line-height:1.25}
.end-sub{font-size:31px;color:var(--muted);line-height:1.7;margin-top:32px}
.tags{display:flex;flex-wrap:wrap;gap:14px;margin-top:52px}
.tags span{font-size:23px;font-weight:700;color:var(--accent);background:var(--pill);
  border:1px solid var(--line);border-radius:999px;padding:12px 22px}
.end-cta{margin-top:60px;background:var(--accent);color:#fff;border-radius:26px;
  padding:34px 40px;font-size:32px;font-weight:800;line-height:1.5;box-shadow:var(--shadow)}
.end-src{margin-top:auto;font-size:19px;color:var(--muted);line-height:1.7;
  border-top:1px solid var(--line);padding-top:26px}
"""

THEMES = {
    "light": """
:root{
  --bg:#f3f6ff;--card:#ffffff;--ink:#0d1b3e;--muted:#64719a;--accent:#3159e8;
  --hot:#f0442f;--hot2:#ff9d2e;--line:rgba(13,27,62,.10);--pill:rgba(49,89,232,.07);
  --grid:rgba(49,89,232,.055);--glow1:rgba(88,132,255,.30);--glow2:rgba(255,138,90,.22);
  --ghost:rgba(49,89,232,.055);--ghost2:rgba(49,89,232,.20);
  --shadow:0 10px 30px rgba(24,45,110,.07);
}""",
    "dark": """
:root{
  --bg:#0a0f1e;--card:#121a30;--ink:#f2f5ff;--muted:#8e9dc0;--accent:#6f92ff;
  --hot:#ff6a48;--hot2:#ffbe4d;--line:rgba(255,255,255,.10);--pill:rgba(111,146,255,.11);
  --grid:rgba(140,170,255,.055);--glow1:rgba(70,110,255,.34);--glow2:rgba(255,90,60,.20);
  --ghost:rgba(160,190,255,.045);--ghost2:rgba(160,190,255,.26);
  --shadow:0 10px 30px rgba(0,0,0,.24);
}""",
}

NUM_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

# 放入 f-string 模板，避免 JS 花括号被当成格式化占位符
FIT_JS = """
document.querySelectorAll('.repo-name').forEach(function(e){
  var s = parseFloat(getComputedStyle(e).fontSize);
  var guard = 0;
  while (e.scrollWidth > e.clientWidth + 2 && s > 24 && guard++ < 40) {
    s -= 1; e.style.fontSize = s + 'px';
  }
});

/* 版面兜底：正文仍超出可用高度时，整体最多缩到 0.92，避免底部被画布裁掉。
   上限按页面纸边与页脚高度静态计算，不随缩放漂移，避免自我追逐式缩小。 */
(function fitPage(){
  var wrap = document.querySelector('.wrap');
  var main = document.querySelector('.main');
  var inner = main && main.querySelector('.inner');
  var ft = document.querySelector('.ft');
  if (!wrap || !main || !inner || !ft) return;
  var padB = parseFloat(getComputedStyle(wrap).paddingBottom) || 0;
  var limit = wrap.getBoundingClientRect().bottom - padB - ft.offsetHeight - 6;
  var avail = limit - main.getBoundingClientRect().top;
  var z = 1, guard = 0;
  while (inner.scrollHeight > avail / z + 1 && z > 0.92 && guard++ < 9) {
    z -= 0.01;
    main.style.zoom = z;
  }
})();
"""


# ---------------------------------------------------------------- helpers

def esc(v):
    return html.escape(str(v if v is not None else ""), quote=True)


def to_int(v, default=0):
    if isinstance(v, int):
        return v
    s = re.sub(r"[^\d\-]", "", str(v or ""))
    try:
        return int(s) if s and s != "-" else default
    except ValueError:
        return default


def fmt(n):
    return f"{to_int(n):,}"


def load_data(args):
    if args.data:
        raw = Path(args.data).read_text(encoding="utf-8")
    elif args.from_md:
        md = Path(args.from_md).read_text(encoding="utf-8")
        m = re.search(r"<!--\s*XHS_DATA_START\s*-->(.*?)<!--\s*XHS_DATA_END\s*-->",
                      md, re.S | re.I)
        if not m:
            raise SystemExit("未在 Markdown 中找到 XHS_DATA 数据块")
        raw = m.group(1).strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I).strip()
    else:
        raise SystemExit("需要 --data 或 --from-md 之一")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise SystemExit("XHS_DATA 不是合法 JSON")
        data = json.loads(m.group(0))

    items = []
    for i, it in enumerate(data.get("items") or [], 1):
        repo = str(it.get("repo") or it.get("project") or "暂无数据")
        owner, _, name = repo.partition("/")
        items.append({
            "rank": to_int(it.get("rank"), i),
            "repo": repo,
            "owner": owner,
            "name": name or owner,
            "lang": str(it.get("lang") or it.get("language") or "暂无数据"),
            "new_stars": to_int(it.get("new_stars") or it.get("today_stars")),
            "total_stars": to_int(it.get("total_stars") or it.get("stars")),
            "one_liner": str(it.get("one_liner") or it.get("desc") or "暂无简介"),
        })
    items.sort(key=lambda x: (-x["new_stars"], x["rank"]))
    for i, it in enumerate(items, 1):
        it["rank"] = i
    data["items"] = items
    data.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
    data.setdefault("window", f"GitHub Trending · daily · {data['date']}")
    data.setdefault("headline", f"一天狂涨 {fmt(items[0]['new_stars'])} 星" if items else "今日 GitHub 飙升榜")
    data.setdefault("subhead", f"GitHub 飙升榜 Top {len(items)}")
    data.setdefault("kicker", "每日 3 分钟，刷完今天涨最猛的开源项目")
    data.setdefault("overview", "今日榜单以 AI Agent 与开发者工具为主。")
    data.setdefault("trends", [])
    data.setdefault("hashtags", ["#程序员", "#Github热门", "#开源项目"])
    data.setdefault("sources", ["https://github.com/trending?since=daily"])
    data.setdefault("note_title", f"GitHub飙升榜｜{data['date']} Top{len(items)}")
    data.setdefault("disclaimer", "数据口径：GitHub Trending 日榜 stars today，按当日新增 star 降序。")
    return data


def page_shell(body, page, total, ghost="", theme="light"):
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>card {page}</title><style>{THEMES[theme]}{CSS}</style></head><body>
<div class="bg-grid"></div><div class="glow g1"></div><div class="glow g2"></div>
{f'<div class="big-num">{esc(ghost)}</div>' if ghost else ''}
<div class="wrap">
  <div class="hd"><div class="brand"><span class="dot"></span>GITHUB 飙升榜</div>
    <div class="date">{esc(DATE_LABEL)}</div></div>
  <div class="main"><div class="inner">{body}</div></div>
  <div class="ft"><div>每日 3 分钟 · 刷完 GitHub 热榜</div>
    <div class="pg mono">{page:02d} / {total:02d}</div></div>
</div>
<script>{FIT_JS}</script>
</body></html>"""


DATE_LABEL = ""


def build_cards(d, theme, per_page):
    global DATE_LABEL
    DATE_LABEL = d["date"].replace("-", ".")
    items = d["items"]
    total_new = sum(x["new_stars"] for x in items)
    langs = len({x["lang"] for x in items if x["lang"] != "暂无数据"})
    chunks = [items[i:i + per_page] for i in range(0, len(items), per_page)] or [[]]
    n = 2 + len(chunks) + 1
    cards, p = [], 1

    # 1. 封面
    pills = "".join(f'<span class="pill">{esc(t)}</span>' for t in d["trends"][:3])
    stats = f"""
      <div class="s"><div class="v hot mono">+{fmt(total_new)}</div><div class="l">Top{len(items)} 今日合计涨星</div></div>
      <div class="s"><div class="v mono">+{fmt(items[0]['new_stars']) if items else 0}</div><div class="l">单日最高</div></div>
      <div class="s"><div class="v mono">{langs}</div><div class="l">覆盖语言</div></div>"""
    body = f"""
      <div class="cover-body">
        <div class="cover-title">一天狂涨<br><span class="num">{fmt(items[0]['new_stars']) if items else 0}</span> 星</div>
        <div class="cover-sub">{esc(d['subhead'])}</div>
        <div class="cover-kicker">{esc(d['kicker'])}</div>
        <div class="cover-pills">{pills}</div>
        <div class="cover-stats">{stats}</div>
      </div>"""
    cards.append(("01-封面", page_shell(body, p, n, "01", theme)))
    p += 1

    # 2. 今日看点
    trends = "".join(
        f'<div class="trend"><div class="n mono">{i:02d}</div><div class="t">{esc(t)}</div></div>'
        for i, t in enumerate(d["trends"][:3], 1))
    stat_row = f"""
      <div class="stat"><div class="v hot mono">+{fmt(total_new)}</div><div class="l">合计涨星</div></div>
      <div class="stat"><div class="v mono">{len(items)}</div><div class="l">上榜项目</div></div>
      <div class="stat"><div class="v mono">{langs}</div><div class="l">编程语言</div></div>"""
    top5 = items[:5]
    mx = max((x["new_stars"] for x in top5), default=1) or 1
    bars = "".join(
        f'<div class="bar"><span class="bn">{esc(x["name"])}</span>'
        f'<div class="track"><i style="width:{max(6, round(x["new_stars"] / mx * 100))}%"></i></div>'
        f'<span class="bv mono">+{fmt(x["new_stars"])}</span></div>' for x in top5)
    body = f"""
      <div class="sec-title">今日看点</div>
      <div class="sec-desc">{esc(d['window'])}</div>
      <div class="overview">{esc(d['overview'])}</div>
      <div class="trends">{trends}</div>
      <div class="bars"><h3>今日涨星分布 · TOP 5</h3>{bars}</div>
      <div class="stat-row">{stat_row}</div>
      <div class="note">{esc(d['disclaimer'])}</div>"""
    cards.append(("02-今日看点", page_shell(body, p, n, "02", theme)))
    p += 1

    # 3..n-1 榜单分页
    for ci, chunk in enumerate(chunks):
        lo = chunk[0]["rank"] if chunk else 0
        hi = chunk[-1]["rank"] if chunk else 0
        rows = []
        for it in chunk:
            size = 46 if len(it["name"]) <= 14 else (40 if len(it["name"]) <= 20 else 34)
            owner_html = (f'<div class="owner-line mono">{esc(it["owner"])} /</div>'
                          if it["owner"] != it["repo"] else "")
            rows.append(f"""
              <div class="row">
                <div class="rk mono">{it['rank']:02d}</div>
                <div class="top">
                  <div class="repo-box">{owner_html}
                    <div class="repo-name" style="font-size:{size}px">{esc(it['name'])}</div></div>
                  <div class="delta mono">+{fmt(it['new_stars'])}<small>stars</small></div>
                </div>
                <div class="meta"><span class="tag">{esc(it['lang'])}</span>
                  <span class="total mono">总 {fmt(it['total_stars'])} ★</span></div>
                <div class="desc">{esc(it['one_liner'])}</div>
              </div>""")
        body = f"""
          <div class="rank-head"><div class="t">Top {lo}–{hi}</div>
            <div class="s">按当日新增 star 降序</div></div>
          <div class="list">{''.join(rows)}</div>"""
        if len(chunk) < per_page:
            full = "".join(
                f'<div class="fr"><span class="n mono">{x["rank"]:02d}</span>'
                f'<span class="nm">{esc(x["repo"])}</span>'
                f'<span class="d mono">+{fmt(x["new_stars"])}</span></div>' for x in items)
            body += f"""<div class="fill-note">榜单到此结束 · 完整项目详情、技术亮点与来源链接见同日 Markdown 报告。</div>
              <div class="full"><h3>今日完整榜单速览</h3>{full}</div>"""
        cards.append((f"{p:02d}-榜单-{lo:02d}-{hi:02d}", page_shell(body, p, n, f"{p:02d}", theme)))
        p += 1

    # 结尾
    tags = "".join(f"<span>{esc(t)}</span>" for t in d["hashtags"])
    body = f"""
      <div class="end-title">你最想<br>试哪个？</div>
      <div class="end-sub">评论区聊聊 👇 也欢迎交换你收藏的神器。<br>关注我，每天 3 分钟刷完 GitHub 热榜，不迷路。</div>
      <div class="tags">{tags}</div>
      <div class="end-cta">完整 Top{len(items)} 详情 / 技术亮点 / 许可证<br>见今日 Markdown 报告</div>
      <div class="end-src">{esc(d['disclaimer'])}<br>来源：{esc(' · '.join(d['sources']))}</div>"""
    cards.append((f"{p:02d}-结尾", page_shell(body, p, n, f"{p:02d}", theme)))
    return cards


def note_markdown(d):
    lines = [f"# {d['note_title']}", "", d["overview"], "",
             "老规矩，每天 3 分钟，带你看完今天涨最猛的开源项目👇", ""]
    for i, it in enumerate(d["items"]):
        emoji = NUM_EMOJI[i] if i < len(NUM_EMOJI) else f"({i+1})"
        lines.append(f"{emoji} {it['name']}：今日 +{fmt(it['new_stars'])} 星。{it['one_liner']}（{it['lang']}，总 {fmt(it['total_stars'])} ★）")
    lines += ["", "你最想试哪个？评论区聊聊👇", "也欢迎交换你收藏的神器。",
              "关注我，每天 3 分钟刷完 GitHub 热榜，不迷路。", "",
              " ".join(d["hashtags"]), "", "---", "",
              f"- 数据口径：{d['window']}", f"- {d['disclaimer']}",
              "- 来源：" + " · ".join(d["sources"]), ""]
    return "\n".join(lines)


def find_chrome(explicit=None):
    if explicit:
        return explicit
    env = shutil.which("chrome") or shutil.which("msedge")
    if env:
        return env
    for p in [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              "/usr/bin/google-chrome", "/usr/bin/chromium"]:
        if Path(p).exists():
            return p
    raise SystemExit("找不到 Chrome/Edge，请用 --chrome 指定路径")


def shoot(chrome, html_path, png_path, idx):
    cmd = [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
           "--force-device-scale-factor=1", f"--window-size={W},{H}",
           "--virtual-time-budget=1800", f"--user-data-dir={html_path.parent / ('_profile' + str(idx))}",
           f"--screenshot={png_path}", html_path.as_uri()]
    r = subprocess.run(cmd, capture_output=True, timeout=90)
    if not png_path.exists():
        raise RuntimeError(f"截图失败: {png_path.name}\n{r.stderr.decode('utf-8', 'ignore')[-600:]}")
    try:
        from PIL import Image
        with Image.open(png_path) as im:
            if im.size != (W, H):
                raise RuntimeError(f"{png_path.name} 尺寸异常 {im.size}")
    except ImportError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--from-md")
    ap.add_argument("--out")
    ap.add_argument("--theme", choices=list(THEMES), default="light")
    ap.add_argument("--per-page", type=int, default=4)
    ap.add_argument("--chrome")
    ap.add_argument("--no-shot", action="store_true")
    args = ap.parse_args()

    d = load_data(args)
    if not d["items"]:
        raise SystemExit("榜单数据为空，拒绝生成空图文")

    out = (Path(args.out) if args.out else ROOT / "pic" / d["date"].replace("-", "") / "xhs").resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "发布文案.md").write_text(note_markdown(d), encoding="utf-8")

    cards = build_cards(d, args.theme, max(1, args.per_page))
    chrome = None if args.no_shot else find_chrome(args.chrome)
    made = []
    for i, (name, doc) in enumerate(cards, 1):
        hp = out / f"_{name}.html"
        hp.write_text(doc, encoding="utf-8")
        if args.no_shot:
            print("HTML:", hp)
            continue
        pp = out / f"{name}.png"
        shoot(chrome, hp, pp, i)
        made.append(pp)
        print(f"[{i}/{len(cards)}] {pp.name}  {pp.stat().st_size // 1024} KB")

    for prof in out.glob("_profile*"):
        if prof.is_dir():
            shutil.rmtree(prof, ignore_errors=True)

    if made:
        thumbs = "".join(
            f'<figure><img src="{p.name}" alt="{esc(p.stem)}"><figcaption>{esc(p.stem)}</figcaption></figure>'
            for p in made)
        (out / "预览.html").write_text(
            f'<!doctype html><meta charset="utf-8"><title>GitHub 飙升榜图文预览 {esc(d["date"])}</title>'
            '<style>body{margin:0;background:#e9edf7;font-family:"Microsoft YaHei",sans-serif}'
            'h1{text-align:center;padding:32px 0 8px;font-size:26px;color:#0d1b3e}'
            'p{text-align:center;color:#5d6b8c;margin:0 0 24px}'
            '.g{display:flex;flex-wrap:wrap;gap:24px;justify-content:center;padding:0 24px 48px}'
            'figure{margin:0;width:360px}img{width:100%;display:block;border-radius:12px;box-shadow:0 8px 28px rgba(20,40,90,.18)}'
            'figcaption{text-align:center;padding:10px;color:#5d6b8c;font-size:14px}</style>'
            f'<h1>GitHub 飙升榜 · 小红书图文 {esc(d["date"])}</h1><p>共 {len(made)} 张 · 1080×1440 · 可直接保存到相册发布</p>'
            f'<div class="g">{thumbs}</div>', encoding="utf-8")
        print("预览页:", out / "预览.html")
    print("发布文案:", out / "发布文案.md")
    print("输出目录:", out)


if __name__ == "__main__":
    main()
