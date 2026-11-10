"""Validate a daily brief, render the cards, and optionally create a WeChat draft."""

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from render_xhs_cards import ROOT, build_cards


def validate_brief(path, date):
    markdown = path.read_text(encoding="utf-8-sig")
    blocks = re.findall(r"<!-- XHS_DATA_START -->(.*?)<!-- XHS_DATA_END -->", markdown, re.S)
    if len(blocks) != 1 or not markdown.rstrip().endswith("<!-- XHS_DATA_END -->"):
        raise ValueError("简报末尾必须有且只有一个 XHS_DATA 数据块")
    data = json.loads(blocks[0])
    if data["date"] != date:
        raise ValueError(f"数据日期 {data['date']} 与执行日期 {date} 不一致")
    items = data["items"]
    if not 1 <= len(items) <= 10:
        raise ValueError("榜单须有 1–10 条真实项目")
    repos = set()
    last = float("inf")
    for rank, item in enumerate(items, 1):
        repo = item["repo"]
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo, re.ASCII) or repo.lower() in repos:
            raise ValueError(f"无效或重复的仓库名 {repo}")
        stars = item["new_stars"]
        if type(item["rank"]) is not int or item["rank"] != rank:
            raise ValueError(f"{repo} 排名必须从 1 连续编号")
        if type(stars) is not int or not 0 <= stars <= last:
            raise ValueError(f"{repo} 新增星数必须为非负整数且按降序排列")
        if type(item["total_stars"]) is not int or item["total_stars"] < stars:
            raise ValueError(f"{repo} 总星数须为不小于新增星数的整数")
        repos.add(repo.lower())
        last = stars
    data["subhead"] = f"GitHub 飙升榜 Top {len(items)}"
    return data


def run(script, *args):
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *map(str, args)],
        cwd=ROOT,
    ).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="YYYYMMDD，默认北京时间当天")
    parser.add_argument("--dry-run", action="store_true", help="在临时目录渲染并校验公众号文案，不上传或归档")
    parser.add_argument("--draft", action="store_true", help="归档图片并创建公众号草稿")
    args = parser.parse_args()
    if args.dry_run and args.draft:
        parser.error("--dry-run 与 --draft 只能选其一")
    today = datetime.now(timezone(timedelta(hours=8))).date()
    date_key = args.date or today.strftime("%Y%m%d")
    try:
        date = datetime.strptime(date_key, "%Y%m%d").date()
        if date.strftime("%Y%m%d") != date_key:
            raise ValueError("日期必须为 YYYYMMDD")
        if args.draft and date != today:
            raise ValueError("每日流水线只向公众号提交北京时间当天的榜单")
        data = validate_brief(ROOT / "articles" / "src" / f"{date_key}-github.md", date.isoformat())
        with TemporaryDirectory(prefix="github-trending-") as temp:
            stage = Path(temp)
            source = stage / "source.json"
            source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            xhs = stage / "xhs"
            if run("render_xhs_cards.py", "--data", source, "--out", xhs):
                raise ValueError("竖版图渲染失败")
            normalized = json.loads((xhs / "data.json").read_text(encoding="utf-8"))
            expected = {f"{name}.png" for name, _ in build_cards(normalized, "light", 4)}
            if {p.name for p in xhs.glob("*.png")} != expected:
                raise ValueError("竖版图缺页")
            if not (stage / "wechat" / "公众号封面.png").is_file():
                raise ValueError("缺少公众号安全封面")
            if args.dry_run:
                return run("push_wechat_newspic.py", "--date", date_key, "--dir", xhs, "--dry-run")
            archive = ROOT / "pic" / date_key
            for name in ("xhs", "wechat"):
                shutil.copytree(stage / name, archive / name, dirs_exist_ok=True)
            for old in (archive / "xhs").glob("*.png"):
                if re.match(r"^\d{2}-", old.name) and old.name not in expected:
                    old.unlink()
            print(f"图片和文案已归档至 {archive}", flush=True)
            if args.draft:
                result = run("push_wechat_newspic.py", "--date", date_key, "--dir", xhs)
                return 0 if result == 3 else result
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"流水线失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
