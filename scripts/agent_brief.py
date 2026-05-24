#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

WORKSPACE = Path('/home/padiac/PrepSignal/backend').resolve()
REPORTS_DIR = Path('/home/padiac/PrepSignal/reports/daily').resolve()
MODEL = os.environ.get('CLAUDE_CODE_MODEL', 'sonnet')
TZ = ZoneInfo('America/Los_Angeles')

PROMPT_TEMPLATE = """你正在分析 {db_path} 及当前 backend 项目里的相关文件。\n\n任务：生成 {report_date} 的 PrepSignal 每日面经简报。\n\n这份简报必须严格遵守下面这套已经多轮验证过的固定格式，不能自由发挥成散文复述。\n\n硬要求：\n1. 优先使用 raw_posts.db / interpreted_posts 的真实数据。\n2. 不要用 decoded_thread.json 代替数据库，除非你明确说明数据库查询失败。\n3. 先过滤掉没信息量的帖子：纯求问、纯招聘、只有情绪没有内容、只有泛标签没有题目细节。\n4. 过滤后剩多少条，就展示多少条，不要人为 cap。\n5. 逐帖摘要必须是“压缩笔记”风格，不要写成长句叙事，不要复述流程，不要写废话。\n6. 严禁写这类无用细节：几分钟自我介绍、哪国裔面试官、在哪个 office、白板/带电脑、收到拒信多久、楼主情绪。\n7. 不要使用省略号，不要截断半句。宁可少写，也要写完整短语。\n8. 如果出现 LeetCode，尽量写“题号 + 题名”，不要只写编号。\n9. Coding 优先写成题目/LC；找不到 LC 时，用极简题意短语。\n10. SD/OOD 只保留一句核心题目，不要展开成长段。\n11. BQ 只保留可复用的问题类型，不要写叙事。\n12. 能合并的中英文同义题要合并，例如 Ad Click System / 广告点击系统。\n13. 重点看点必须是具体题目/主题，不要只写公司名。\n14. 重点看点不要套话，不要出现“信息密度高、值得看、准备方向明确”这种空话。\n15. 不要展示过滤掉的帖子，不要写数据源，不要附加解释，不要加“一句话总结”。\n16. 输出必须以 `# PrepSignal 每日面经简报（MM-DD）` 这一行开头，前面不能有任何说明、引导语、元信息、过滤说明、数据范围、保存路径。\n17. 在“5 个重点看点”结束后立即停止，后面不能再追加任何说明。\n\n逐帖摘要固定格式：\n- **公司/轮次**: Coding（题1, 题2）+ SD（题）+ OOD（题）+ BQ（点）\n\n规则：\n- 有哪几类就写哪几类，没有就不写。\n- 一条尽量保持一行。\n- Coding 放前面，SD/OOD 其次，BQ 最后。\n- 不允许写成长段描述。\n\n“5 个重点看点”固定格式：\n1. **具体题目/主题**（公司/轮次）：用 1-2 句说明为什么它重要，考什么，特别点是什么。\n\n输出格式：\n# PrepSignal 每日面经简报（MM-DD）\n\n## 一、逐帖摘要\n- 每条一行，严格按固定格式\n\n## 二、5 个重点看点\n1. ...\n"""


def find_claude() -> str:
    env = os.environ.get('CLAUDE_CODE_PATH')
    if env and Path(env).exists():
        return env
    candidates = (
        '/mnt/c/Users/pppad/AppData/Roaming/npm/claude',
        '/home/padiac/.local/bin/claude',
    )
    for path in candidates:
        if Path(path).exists():
            return path
    found = shutil.which('claude')
    if found:
        return found
    raise SystemExit('claude CLI not found in PATH')


def main() -> int:
    report_date = sys.argv[1] if len(sys.argv) > 1 else datetime.now(TZ).date().isoformat()
    prompt = PROMPT_TEMPLATE.format(db_path=WORKSPACE / 'raw_posts.db', report_date=report_date)
    claude = find_claude()
    # Tool selection per task: daily brief needs to query SQLite (Bash) and
    # explore the backend dir (Read/Glob/Grep). Allow WebSearch/WebFetch to
    # verify 黑话/中文LC题号 (same as knowledge_worker). Block Edit/Write —
    # this is read-only analysis. --setting-sources "" skips CLAUDE.md/skills
    # which are about repo development, not about generating briefs.
    args = [
        claude,
        '-p', prompt,
        '--output-format', 'text',
        '--tools', 'Bash,Read,Glob,Grep,WebSearch,WebFetch',
        '--setting-sources', '',
        '--add-dir', str(WORKSPACE),
        '--dangerously-skip-permissions',
        '--model', MODEL,
    ]
    result = subprocess.run(
        args,
        cwd=str(WORKSPACE),
        text=True,
        capture_output=True,
        timeout=900,
    )
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        return result.returncode or 1
    text = (result.stdout or '').strip()
    marker = '# PrepSignal 每日面经简报'
    idx = text.find(marker)
    if idx != -1:
        text = text[idx:]
        print(text)
        return 0

    brief_path = REPORTS_DIR / f'brief_{report_date}.md'
    if brief_path.exists():
        print(brief_path.read_text(encoding='utf-8').strip())
        return 0

    print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
