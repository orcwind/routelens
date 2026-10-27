"""章节名归一化：简中 / 繁中 / 英文 Client.txt 统一为「第一章」…「第五章」。"""

from __future__ import annotations

import re

POE2_CHAPTER_ORDER: tuple[str, ...] = (
    "第一章",
    "第二章",
    "第三章",
    "第四章",
    "第五章",
)

POE2_IGNORED_CHAPTER_LABELS: frozenset[str] = frozenset(
    {"第六章", "Act 6", "第六章", "第6章", "Chapter 6"}
)

POE2_ALL_CHAPTER_NAMES: frozenset[str] = frozenset(
    {
        *POE2_CHAPTER_ORDER,
        *POE2_IGNORED_CHAPTER_LABELS,
        "Act 1",
        "Act 2",
        "Act 3",
        "Act 4",
        "Act 5",
        "Chapter 1",
        "Chapter 2",
        "Chapter 3",
        "Chapter 4",
        "Chapter 5",
        "第1章",
        "第2章",
        "第3章",
        "第4章",
        "第5章",
    }
)

# 各语言章节标签 → 规范章节（第一章…）
_CHAPTER_ALIAS_TO_CANONICAL: dict[str, str] = {}
for index, canonical in enumerate(POE2_CHAPTER_ORDER, start=1):
    _CHAPTER_ALIAS_TO_CANONICAL[canonical] = canonical
    _CHAPTER_ALIAS_TO_CANONICAL[f"第{index}章"] = canonical
    _CHAPTER_ALIAS_TO_CANONICAL[f"第{index}章"] = canonical
    _CHAPTER_ALIAS_TO_CANONICAL[f"Act {index}"] = canonical
    _CHAPTER_ALIAS_TO_CANONICAL[f"Act{index}"] = canonical
    _CHAPTER_ALIAS_TO_CANONICAL[f"ACT {index}"] = canonical
    _CHAPTER_ALIAS_TO_CANONICAL[f"Chapter {index}"] = canonical
    _CHAPTER_ALIAS_TO_CANONICAL[f"chapter {index}"] = canonical

_ACT_RE = re.compile(r"^Act\s*(\d+)\s*$", re.IGNORECASE)
_CHAPTER_NUM_RE = re.compile(r"^第\s*(\d+)\s*章\s*$")
_CHAPTER_EN_RE = re.compile(r"^Chapter\s*(\d+)\s*$", re.IGNORECASE)


def normalize_poe2_chapter(name: str) -> str | None:
    """将日志中的章节标签转为规范「第N章」；无效或误写标签返回 None。"""
    raw = (name or "").strip()
    if not raw or raw in POE2_IGNORED_CHAPTER_LABELS:
        return None

    direct = _CHAPTER_ALIAS_TO_CANONICAL.get(raw)
    if direct:
        return direct

    act_match = _ACT_RE.match(raw)
    if act_match:
        return _chapter_index_to_canonical(int(act_match.group(1)))

    chapter_match = _CHAPTER_NUM_RE.match(raw)
    if chapter_match:
        return _chapter_index_to_canonical(int(chapter_match.group(1)))

    en_match = _CHAPTER_EN_RE.match(raw)
    if en_match:
        return _chapter_index_to_canonical(int(en_match.group(1)))

    return None


def _chapter_index_to_canonical(index: int) -> str | None:
    if 1 <= index <= len(POE2_CHAPTER_ORDER):
        return POE2_CHAPTER_ORDER[index - 1]
    return None


def chapter_display_name(canonical: str, locale: str) -> str:
    """按界面语言显示章节名。"""
    if canonical not in POE2_CHAPTER_ORDER:
        # PoE1 的「第7章」等：英文界面显示 Act 7
        match = _CHAPTER_NUM_RE.match(canonical or "")
        if match and locale == "en":
            return f"Act {int(match.group(1))}"
        return canonical
    index = POE2_CHAPTER_ORDER.index(canonical) + 1
    if locale == "en":
        return f"Act {index}"
    return canonical


_CHAPTER_NUM_ANY_RE = re.compile(r"^第\s*(\d+)\s*章\s*$")
# 中文数字章节：第一章 … 第十章
_CHAPTER_CN_RE = re.compile(r"^第\s*([零一二三四五六七八九十]+)\s*章\s*$")
_CN_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def _cn_to_int(text: str) -> int:
    """中文数字 → int（一 → 1，十 → 10，十二 → 12；其余按位解析）。"""
    raw = (text or "").strip()
    if not raw:
        return -1
    if raw == "十":
        return 10
    if raw.startswith("十"):
        return 10 + _CN_DIGITS.get(raw[1:], 0)
    if "十" in raw:
        head, _, tail = raw.partition("十")
        return _CN_DIGITS.get(head, 0) * 10 + (_CN_DIGITS.get(tail, 0) if tail else 0)
    return _CN_DIGITS.get(raw, -1)


def chapter_sort_index(chapter: str) -> int:
    """章节标签的排序键（按幕号从小到大）；无法识别返回一个很大值。"""
    raw = str(chapter or "").strip()
    if not raw:
        return 10**6
    match = _CHAPTER_NUM_ANY_RE.match(raw)
    if match:
        return int(match.group(1))
    match = _CHAPTER_CN_RE.match(raw)
    if match:
        value = _cn_to_int(match.group(1))
        if value > 0:
            return value
    match = _ACT_RE.match(raw) or _CHAPTER_EN_RE.match(raw)
    if match:
        return int(match.group(1))
    return 10**6


def sort_chapters(chapters: list[str]) -> list[str]:
    """章节按幕号排序（去重保序）。

    日志里的章节读取顺序可能是「第四章 → 第一章 → 第二章」：
    角色先在终局城镇上线、再新建角色从第一幕开始。
    路线名必须按幕号显示成「第一章 → 第四章」，不能照抄读取顺序。
    """
    ordered: list[str] = []
    for chapter in chapters or []:
        name = str(chapter or "").strip()
        if name and name not in ordered:
            ordered.append(name)
    return sorted(ordered, key=chapter_sort_index)
