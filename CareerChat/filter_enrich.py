"""Single-shot LLM call: read a thread, decide if it's worth pushing,
and if yes, produce a Telegram-ready Chinese markdown briefing.

Uses Claude Code CLI with --json-schema for guaranteed structured output.
WebSearch enabled so the model can verify jargon (L66, GVSA, PIP variants...).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

_SCHEMA = {
    "type": "object",
    "properties": {
        "worth": {"type": "boolean"},
        "reason": {"type": "string"},
        "telegram_markdown": {"type": ["string", "null"]},
    },
    "required": ["worth", "reason"],
}

PROMPT = """你是我的私人职场观察员，帮我（对中美职场黑话/江湖不熟的人）从一亩三分地"职场达人"板块挖出值得知道的东西。

# 重要：先看黑话词典
下面是一份一亩三分地常用黑话词典。**碰到帖子里出现的术语，优先用词典里的释义**——尤其是 emoji 化的公司绰号（🦑=Meta、巨硬=Microsoft 等），这些靠推理和搜索很难猜中。词典里没有的再 WebSearch 或推理。

{glossary}

---

# 输入
一篇论坛帖子（主楼 + 回帖）。

# 第一步：判断这帖值不值得推给我（偏宽松）

❌ skip 的：纯打卡/签到、几个字的吐槽、纯求 refer 没内容、秀娃秀车秀房、纯广告

✅ 推（宁可宽松）：
- 反映行业/公司现象（招聘冷热、layoff、政策、文化）
- 个人遭遇有故事（PIP、被裁、conflict、转组、签证、谈判）
- 求建议且讨论有质量
- 跳槽/offer/comp 数字
- 任何能让我多懂一点职场生态的讨论
- 主帖一般但回帖有亮点也算

# 第二步：如果值得推，给我写一段 Telegram 中文消息

## 硬性要求（只有 3 条）

1. 第一行：`*[原帖标题]*`
2. 第二行：`🔗 [原帖链接](URL)`
3. 总长度 ≤ 1500 字符

## 软性要求

**剩下的内容你自由发挥**。你像一个聪明的、信息量大的朋友，看完这帖之后凑过来给我讲：「哎你看这个事啊…」。

这帖最值得讲的角度是什么？你自己挑。下面是一些常用武器，你按这帖的特征选 2-5 个组合，不要每条都用，也不要按固定顺序：

- 🎯 主帖到底在说什么（如果故事不是一眼能看懂，给我讲清楚）
- 📖 黑话/缩写/职级/公司绰号解释（碰到才解释，没有就不写。不确定的用 WebSearch 查）
- 💰 薪资/职级映射（如果涉及，给个范围或对标，比如 L66 ≈ Meta E5 ≈ Google L5）
- 💬 回帖里值得记下的观点 / 哪些是 BS 哪些靠谱
- 🔍 帖子里没明说但可推断的事（弦外之音、作者实际在焦虑啥）
- 🌡️ 信号解读（这反映了什么趋势/现象/行情）
- 🆚 对比类比（"这跟去年 Google 那波很像"、"这个 manager 行为典型 micromanage"）
- 💡 你的判断 / "如果是我会怎么做" / 哪条路实际可行
- ❓ 这帖让你想到的、值得我以后留意的后续问题
- 📊 数字 / 时间线 / 量化的信息（如果原帖里有）
- ……或者你当下灵光一闪觉得有意思的别的角度

## 风格

- Telegram Markdown：`*粗体*`、`[文字](URL)`、emoji 适量
- 写得像人话，不要"综上所述"、"基于以上"这种作文腔
- 可以有观点，可以说"这个回帖说错了"
- 短句、分段、易扫
- 别为凑长度灌水。900-1500 字符是甜区，特别简单的帖 500 字也行

# 输出 JSON
{{
  "worth": true | false,
  "reason": "10-30 字说明判断依据",
  "telegram_markdown": "完整 markdown 文本"  // 仅 worth=true 时填，false 时 null
}}

# 帖子信息
标题: {title}
URL: {url}
板块标签: {category}
作者: {author}

---
{content}
"""


def _find_claude_binary() -> str | None:
    p = os.environ.get("CLAUDE_CODE_PATH")
    if p and os.path.isfile(p):
        return p
    return shutil.which("claude") or "/mnt/c/Users/pppad/AppData/Roaming/npm/claude"


def call_llm(
    title: str,
    url: str,
    content: str,
    category: str | None = None,
    author: str | None = None,
) -> tuple[dict, str]:
    """Returns ({"worth": bool, "reason": str, "telegram_markdown": str|None}, model_name)."""
    claude = _find_claude_binary()
    if not claude or not os.path.isfile(claude):
        raise RuntimeError("Claude Code CLI not found")
    model = os.environ.get("CLAUDE_CODE_MODEL", "sonnet")
    glossary_path = Path(__file__).parent / "glossary.md"
    glossary = glossary_path.read_text(encoding="utf-8") if glossary_path.exists() else ""
    prompt = PROMPT.format(
        glossary=glossary,
        title=title,
        url=url,
        category=category or "(无)",
        author=author or "(匿名)",
        content=content,
    )
    args = [
        claude,
        "-p", prompt,
        "--output-format", "json",
        "--json-schema", json.dumps(_SCHEMA),
        "--tools", "WebSearch,WebFetch",
        "--setting-sources", "",
        "--model", model,
    ]
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(Path(__file__).parent.resolve()),
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude failed (exit {result.returncode}): {result.stderr or result.stdout}")
    raw = (result.stdout or "").strip()
    if not raw:
        raise RuntimeError("claude returned empty output")
    wrapper = json.loads(raw)
    if wrapper.get("is_error"):
        raise RuntimeError(f"claude API error: {wrapper.get('result') or wrapper}")
    structured = wrapper.get("structured_output")
    if not structured:
        raise RuntimeError(f"claude returned no structured_output; stop_reason={wrapper.get('stop_reason')}")
    return structured, f"claude-code/{model}"
