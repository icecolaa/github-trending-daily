# 每日 GitHub 飙升榜 · 简报与小红书图文

每天抓一次 GitHub Trending 日榜（stars today），产出一份可读的 Markdown 简报，外加一套能直接发小红书的竖版图文卡片，并自动同步到两个远端仓库。

数据全部来自公开页面，不编造、不用旧数据冒充当天。

## 示例产物

2026-11-04：Top10 合计 **+13,886** 星，榜首 `vercel-labs/agent-desktop` 单日 **+2,463** 星。

| 封面 | 今日看点 | 榜单 |
| --- | --- | --- |
| ![封面](pic/20261104/xhs/01-封面.png) | ![今日看点](pic/20261104/xhs/02-今日看点.png) | ![榜单](pic/20261104/xhs/03-榜单-01-04.png) |

完整一套 6 张在 [`pic/20261104/xhs/`](pic/20261104/xhs/)，发布文案在 [`发布文案.md`](pic/20261104/xhs/发布文案.md)。

## 每天怎么跑

| 时间 | 位置 | 做什么 | 产物 |
| --- | --- | --- | --- |
| 08:45 | 云端 | 抓榜单，写详情报告 + 图文文案 + 结构化数据块 | 消息推送正文 |
| 09:10 | 本机 | 独立抓榜，出 6 张竖版图，提交并推送双远端 | `articles/src/<日期>-github.md`、`pic/<日期>/xhs/` |

云端任务关机也能跑，只推送文字；本机任务需要电脑开机，负责出图与同步。

## 目录

```
articles/src/          每日简报（Markdown + 末尾 XHS_DATA 数据块）
pic/<日期>/xhs/        当天图文：6 张 PNG、发布文案.md、预览.html、data.json
scripts/
  render_xhs_cards.py  榜单数据 → 1080×1440 竖版卡片
  sync_remotes.py      提交并推送到多个远端
```

## 本地跑一遍

```bash
# 从简报里抠出数据块，生成整组图文
python scripts/render_xhs_cards.py --from-md articles/src/20261104-github.md

# 也可以直接喂 JSON
python scripts/render_xhs_cards.py --data articles/src/20261104-github-trending-xhs.json

# 深色主题 / 每页 3 个项目 / 指定输出目录
python scripts/render_xhs_cards.py --from-md <file> --theme dark --per-page 3 --out pic/xxx

# 提交并同步到所有远端
python scripts/sync_remotes.py --message "daily: 2026-11-04 GitHub 飙升榜 Top10"
```

出图依赖本机 Chrome 或 Edge 的无头截图能力，中文字体用系统微软雅黑。

## 图文规格

- 1080×1440，共 6 张：封面 / 今日看点（含 Top5 涨星条形图）/ 榜单 3 页 / 结尾
- 长仓库名自动缩字号，不折行、不截断
- 同目录附带 `发布文案.md`（标题 + 逐条点评 + 话题标签）、`预览.html`、`data.json`

## 数据口径

- 榜单口径为 GitHub Trending 日榜的 stars today，按当日新增 star 降序排列
- 总 star 为抓取时页面数值，会随时间变化
- 抓不到的字段标注「暂无数据」，不确定的标注「待核实」
- 每晚抓取后会写明数据窗口与抓取时间

## 声明

数据来自 GitHub 公开页面，本仓库只做整理与可视化，项目版权归各仓库作者所有。
