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
        "push_to_telegram": {"type": "boolean"},
        "push_reason": {"type": "string"},
    },
    "required": ["worth", "reason", "push_to_telegram", "push_reason"],
}

PROMPT = r"""你是我的私人职场观察员，帮我（对中美职场黑话/江湖不熟的人）从一亩三分地"职场达人"板块挖出值得知道的东西。

# 重要：先看黑话词典
下面是一份一亩三分地常用黑话词典。**碰到帖子里出现的术语，优先用词典里的释义**——尤其是 emoji 化的公司绰号（🦑=Meta、巨硬=Microsoft 等），这些靠推理和搜索很难猜中。词典里没有的再 WebSearch 或推理。

{glossary}

---

# 输入
一篇论坛帖子（主楼 + 回帖）。

# 两层判断（重要 — 两个维度独立）

## 第一层：`worth`（内容是否有挖掘价值，**偏宽松**）

❌ `worth=false` 的（不生成 enriched_md，直接 skip）：
- 纯打卡/签到/月度活动
- 几个字的吐槽没具体内容
- 纯求 refer 没任何讨论
- 秀娃/秀车/秀房
- 纯广告/招聘
- 重复月经帖且没新观点

✅ `worth=true` 的（生成 enriched_md，**宁可宽松**）：
- 反映行业/公司现象（招聘冷热、layoff、政策、文化）
- 个人遭遇有故事（PIP、被裁、conflict、转组、签证、谈判）
- 跳槽/offer/comp 数字
- 任何能让我多懂一点职场生态的讨论
- 主帖一般但回帖有亮点也算
- 甚至单楼牢骚帖，只要透露出某个公司/趋势/现象的信号，也算 worth

## 第二层：`push_to_telegram`（讨论度是否够推送，**偏严**）

仅当 `worth=true` 时这一层才生效。决定要不要现在打扰我推 Telegram，还是只默默存档供以后周报趋势分析用。

🚫 `push_to_telegram=false`（**存档不推**）：
- 0-2 条回复，且回帖无信息量（"+1"、"加油"、"惨"、表情包）
- 全是同质化点头/感谢，没人补充任何新东西
- 没有任何反对意见、争议、深度补充
- 主帖独白 + 无人接话的牢骚
- 即使主帖故事感人，但讨论已经死了

✅ `push_to_telegram=true`（**推 Telegram**）：
- 多条回帖且有实质信息量（具体数字、内部情况、专业见解）
- 有争议 / 反驳 / 多视角碰撞
- 楼主和回帖人有深度互动
- 即使只有 1-2 条回复，但回帖本身**信息密度极高**（如行业老兵爆料、内部人员透露具体数字、点破弦外之音）
- 行业信号特别强（如同一周内多个相似帖子反映某趋势）

判断原则：**"如果我读完这帖只感觉'哦'，那就 archive；如果我读完会想'卧槽这个有意思想找人聊'，那就 push"**。

# 写 telegram_markdown（仅当 worth=true）

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

- Telegram **Legacy Markdown**（不是 MarkdownV2）：`*粗体*`、`[文字](URL)`、emoji 适量
- **不要主动加反斜杠 `\` 转义任何字符**。直接写正常字符即可，我们用 legacy Markdown 模式，规则宽松
- 写得像人话，不要"综上所述"、"基于以上"这种作文腔
- 可以有观点，可以说"这个回帖说错了"
- 短句、分段、易扫
- 别为凑长度灌水。900-1500 字符是甜区，特别简单的帖 500 字也行

## 数字纪律（很重要，AI 容易在这里翻车）

涉及钱、股票、TC 计算时必须诚实算账，不能照搬别人的结论：

1. **TC 不是单一数字，是结构**：base + bonus + RSU（按 grant 价计）+ 可能的 signon。典型大厂 SWE：base ~60-70%、RSU ~25-35%、bonus ~10-15%。
2. **股价涨跌只影响 RSU 部分**。base 和 bonus 不会跟股价变。所以"股价 3x → 总 TC 3x"是错的。
3. **算多年收入时分开算**：base × 年数 + RSU vest 后的实际金额 + bonus 累计。
4. **不要全盘相信回帖的数字结论**。回帖经常用感性夸张算法（"早去就是几百万差距！"）。你看到这种数字，自己拆一遍验证再用。如果原帖/回帖给的数字算法明显有问题，**直接指出来**比照搬更有价值。
5. **没把握就承认**："这里粗略估计约 X-Y，具体取决于 refresher 节奏和 vest 时点。"
   比"精确到小数点但是错的"强 10 倍。
6. **不知道就 WebSearch**：某公司股价历史、某级别 TC 范围、vest 结构这些有公开数据，不确定就查。

# 输出 JSON
{{
  "worth": true | false,                       // 第一层：内容是否有价值（偏宽）
  "reason": "10-30 字说明 worth 的判断依据",
  "telegram_markdown": "完整 markdown 文本",   // 仅 worth=true 时填，false 时 null
  "push_to_telegram": true | false,            // 第二层：讨论度是否够推送（偏严）
                                                //   worth=false 时必为 false
                                                //   worth=true + push=false → 存档不推
                                                //   worth=true + push=true → 推 Telegram
  "push_reason": "10-30 字说明 push 的判断依据" // 不论 push 是 true 还是 false 都要给理由
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
