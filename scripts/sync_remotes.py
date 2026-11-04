# -*- coding: utf-8 -*-
"""
把当日新增内容提交并同步到多个 git 远端（双远端 / 多远端镜像）。

用法:
  python scripts/sync_remotes.py                       # 提交并推送到所有已配置 remote
  python scripts/sync_remotes.py -m "daily: 2026-11-04" # 自定义提交信息
  python scripts/sync_remotes.py --remotes origin,mirror
  python scripts/sync_remotes.py --dry-run             # 只看会做什么

行为:
  1. git add -A
  2. 没有变更就跳过提交（仍会尝试把本地领先的提交推上去）
  3. 逐个 remote 执行 git push，互不影响；某个失败只记录，不中断其他远端
  4. 绝不 force push，绝不再删历史；结果写入 .build/sync.log

退出码: 0 全部成功 / 1 有远端推送失败 / 2 没有配置任何远端
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / ".build" / "sync.log"
TIMEOUT = 180


def git(*args, timeout=TIMEOUT):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="ignore", timeout=timeout)


def log(line):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


def branch():
    r = git("rev-parse", "--abbrev-ref", "HEAD")
    name = r.stdout.strip()
    return name if r.returncode == 0 and name and name != "HEAD" else "main"


def remotes():
    r = git("remote")
    return [x.strip() for x in r.stdout.splitlines() if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", "--message")
    ap.add_argument("--remotes", help="逗号分隔，默认全部 remote")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        print("✗ 当前目录不是 git 仓库，先执行 git init -b main")
        return 2

    names = [s.strip() for s in args.remotes.split(",")] if args.remotes else remotes()
    names = [n for n in names if n]
    if not names:
        print("✗ 还没有配置任何远端。先执行:")
        print("  git remote add origin <github 仓库地址>")
        print("  git remote add mirror <第二个仓库地址>")
        return 2

    br = branch()
    msg = args.message or f"daily: {datetime.now():%Y-%m-%d %H:%M} 内容归档"

    def out(s):
        print(s)
        log(s)

    out(f"== 同步开始 {datetime.now():%Y-%m-%d %H:%M:%S} · 分支 {br} · 远端 {', '.join(names)}")

    if not args.dry_run:
        add = git("add", "-A")
        if add.returncode != 0:
            out(f"✗ git add 失败: {add.stderr.strip()[:200]}")
            return 1

        staged = git("diff", "--cached", "--quiet").returncode != 0
        if staged:
            c = git("commit", "-m", msg)
            if c.returncode != 0:
                out(f"✗ git commit 失败: {(c.stderr or c.stdout).strip()[:300]}")
                return 1
            first = git("log", "-1", "--pretty=%h %s").stdout.strip()
            out(f"✓ 已提交 {first}")
        else:
            out("· 工作区无变更，跳过提交")
    else:
        out(f"· [dry-run] 将提交信息: {msg}")

    results = {}
    for i, name in enumerate(names, 1):
        if args.dry_run:
            results[name] = {"ok": None, "detail": "dry-run"}
            out(f"[{i}/{len(names)}] {name} —— 跳过（dry-run）")
            continue
        try:
            p = git("push", name, f"{br}:{br}")
        except subprocess.TimeoutExpired:
            results[name] = {"ok": False, "detail": "推送超时"}
            out(f"[{i}/{len(names)}] ✗ {name} —— 推送超时（>{TIMEOUT}s）")
            continue

        if p.returncode == 0:
            results[name] = {"ok": True, "detail": (p.stderr or "").strip()[-300:]}
            out(f"[{i}/{len(names)}] ✓ {name} —— 已推送")
        else:
            err = (p.stderr or p.stdout).strip()
            hint = ""
            if "rejected" in err or "non-fast-forward" in err:
                hint = "（远端已有新提交，先 git pull --rebase 再推）"
            elif "does not exist" in err or "not found" in err or "Repository not found" in err:
                hint = "（远端仓库不存在或没有权限，先创建空仓库并确认地址）"
            elif "Permission denied" in err or "authentication" in err.lower():
                hint = "（认证失败，检查 SSH key 是否已加到平台）"
            results[name] = {"ok": False, "detail": err[-400:]}
            out(f"[{i}/{len(names)}] ✗ {name} —— 推送失败{hint}")
            out("    " + err.replace("\n", " ")[:260])

    ok = [k for k, v in results.items() if v.get("ok")]
    bad = [k for k, v in results.items() if v.get("ok") is False]
    out(f"== 同步结束：成功 {len(ok)}/{len(names)}{'，失败: ' + ', '.join(bad) if bad else ''}")
    out(json.dumps(results, ensure_ascii=False))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
