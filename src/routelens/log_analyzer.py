from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .area_registry import AreaRegistry
from .games.base import GameProfile
from .games.registry import get_game
from .log_parser import CLIENT_ID_RE, FOREIGN_CLIENT_IDS, GENERATING_AREA_RE, SCENE_RE

TIMESTAMP_RE = re.compile(r"^([0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})")
LOADING_RE = re.compile(r"\[LOADING SCREEN\] \((.+?)\)")
ENTERED_RE = re.compile(r": You have entered (.+)\.?")
ENTERED_CN_TW_RE = re.compile(r"[:：]\s*你(?:已經|已经)?進入\s*(.+?)\s*。")
ENTERED_CN_CN_RE = re.compile(r"[:：]\s*你(?:已经|已經)?进入\s*(.+?)\s*。")
CHAR_CN_RE = re.compile(r": (.+?)[（(](.+?)[）)]目前等[級级]：?\s*(\d+)")
CHAR_EN_RE = re.compile(r": (.+?) \((.+?)\) is now level ([0-9]+)")
DEATH_CN_RE = re.compile(r": (.+?) 被[殺杀][害死]了。")
DEATH_EN_RE = re.compile(r": You have died ([0-9]+) times\.")
COMPANION_AREA_RE = re.compile(r"\[COMPANION\] \[AREA\] (.+)$")
# area id / client id 的常量统一在 log_parser 里定义（此处从那里导入）


@dataclass
class AreaVisit:
    area: str
    timestamp: datetime
    chapter: str = ""
    area_id: str = ""


@dataclass
class SplitNode:
    index: int
    area: str
    area_en: str
    display: str
    segment_seconds: float
    arrived_at: datetime
    area_id: str = ""
    # 重复进入同一地点时，并回首次出现节点的序号；None = 该节点独立保留
    merged_into: int | None = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "area": self.area,
            "area_en": self.area_en,
            "display": self.display,
            "segment_seconds": self.segment_seconds,
            "arrived_at": self.arrived_at.isoformat(),
            "area_id": self.area_id,
        }


@dataclass
class LogRunSession:
    session_id: int
    character: str
    chapters: list[str] = field(default_factory=list)
    visits: list[AreaVisit] = field(default_factory=list)
    deaths: int = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @property
    def chapter_label(self) -> str:
        if not self.chapters:
            return "未知"
        if len(self.chapters) == 1:
            return self.chapters[0]
        return f"{self.chapters[0]} → {self.chapters[-1]}"

    @property
    def total_seconds(self) -> float:
        nodes = self.build_splits()
        return sum(node.segment_seconds for node in nodes)

    @property
    def node_count(self) -> int:
        return len(self.build_splits())

    def build_splits(
        self,
        locale: str = "zh_tw",
        area_registry: AreaRegistry | None = None,
        chapters_filter: set[str] | None = None,
    ) -> list[SplitNode]:
        """进入下一区时，把停留时长写到上一区（刚离开的节点），与实时计时一致。

        **去重规则**：同一地点（area id）只保留第一次出现的节点。
        玩家从 Act 3 回到 Act 1、或在同一幕内两个地点来回跑，
        重复进入的地点不再作为新节点出现。

        但**停留时间不能丢**：重复进入的那段时间并回该地点的原节点，
        这样「各节点用时之和」仍然等于实际总时长。

        身份用 area id 而非区域名：PoE1 的 Act 5 与 Act 10 区域名几乎相同
        （实测 200 个区域名中 34 个跨幕重名），按名字去重会把后半程整段吃掉。
        """
        splits: list[SplitNode] = []
        last_time: datetime | None = None

        # ── 阶段 1：按进入顺序建节点，每段用时 = 离开该区到下次进入的间隔 ──
        for visit in self.visits:
            if chapters_filter is not None and visit.chapter not in chapters_filter:
                continue
            if splits and last_time is not None:
                splits[-1].segment_seconds = max(
                    0.0, (visit.timestamp - last_time).total_seconds()
                )
            splits.append(
                SplitNode(
                    index=len(splits) + 1,
                    area=visit.area,
                    area_en=visit.area,
                    display=visit.area,
                    segment_seconds=0.0,
                    arrived_at=visit.timestamp,
                    area_id=visit.area_id,
                )
            )
            last_time = visit.timestamp

        # ── 阶段 2：同一地点只保留首次出现，其余时间并回原节点 ──
        first_index_by_identity: dict[str, int] = {}
        for index, split in enumerate(splits):
            identity = self._split_identity(split)
            if identity in first_index_by_identity:
                original = splits[first_index_by_identity[identity]]
                original.segment_seconds += split.segment_seconds
                split.merged_into = original.index
                continue
            first_index_by_identity[identity] = index

        return [s for s in splits if s.merged_into is None]

    @staticmethod
    def _split_identity(split: SplitNode) -> str:
        """节点去重身份：有 area id 用 area id（唯一标识一个区域实例），否则用区域名。"""
        if split.area_id:
            return f"{split.area}#{split.area_id}"
        return split.area

    def filtered_chapter_label(self, chapters_filter: set[str] | None = None) -> str:
        if chapters_filter:
            ordered = [chapter for chapter in self.chapters if chapter in chapters_filter]
            if ordered:
                if len(ordered) == 1:
                    return ordered[0]
                return f"{ordered[0]} → {ordered[-1]}"
        return self.chapter_label

    def to_dict(
        self,
        locale: str = "zh_tw",
        area_registry: AreaRegistry | None = None,
        chapters_filter: set[str] | None = None,
    ) -> dict:
        nodes = self.build_splits(locale, area_registry, chapters_filter)
        total_seconds = sum(node.segment_seconds for node in nodes)
        return {
            "session_id": self.session_id,
            "character": self.character,
            "chapters": self.chapters,
            "chapter_label": self.filtered_chapter_label(chapters_filter),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "total_seconds": total_seconds,
            "node_count": len(nodes),
            "deaths": self.deaths,
            "splits": [node.to_dict() for node in nodes],
        }


def parse_timestamp(line: str) -> datetime | None:
    match = TIMESTAMP_RE.match(line)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y/%m/%d %H:%M:%S")


def extract_area(line: str, skip_names: set[str], chapter_names: set[str]) -> str | None:
    from .hideout_filter import is_hideout_area

    companion_match = COMPANION_AREA_RE.search(line)
    if companion_match:
        area = companion_match.group(1).strip()
        if area and area not in skip_names and not is_hideout_area(area):
            return area

    for pattern in (SCENE_RE, LOADING_RE, ENTERED_RE, ENTERED_CN_TW_RE, ENTERED_CN_CN_RE):
        match = pattern.search(line)
        if match:
            area = match.group(1).strip().rstrip(".")
            if area in skip_names or area in chapter_names:
                return None
            if is_hideout_area(area):
                return None
            return area
    return None


def discover_chapters_in_log(path: Path, game_id: str | None = "poe2") -> list[str]:
    profile = get_game(game_id)
    chapter_names = set(profile.chapter_names)
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = SCENE_RE.search(line)
        if not match:
            continue
        raw_name = match.group(1).strip()
        if game_id == "poe2" or game_id is None:
            from .chapter_normalize import normalize_poe2_chapter

            name = normalize_poe2_chapter(raw_name)
            if name:
                found.add(name)
        elif raw_name in chapter_names:
            found.add(raw_name)

    from .chapter_normalize import POE2_CHAPTER_ORDER, normalize_poe2_chapter

    ordered = [chapter for chapter in POE2_CHAPTER_ORDER if chapter in found]
    return ordered


def _extract_character_name(line: str) -> str | None:
    char_cn = CHAR_CN_RE.search(line)
    if char_cn:
        return char_cn.group(1)
    char_en = CHAR_EN_RE.search(line)
    if char_en:
        return char_en.group(1)
    return None


def _start_new_session(
    sessions: list[LogRunSession],
    character: str = "",
) -> LogRunSession:
    return LogRunSession(session_id=len(sessions) + 1, character=character)


def _session_time_bounds(session: LogRunSession) -> None:
    if not session.visits:
        session.started_at = None
        session.ended_at = None
        return
    session.started_at = session.visits[0].timestamp
    session.ended_at = session.visits[-1].timestamp


def _split_trailing_visits_after_idle(
    session: LogRunSession,
    idle_seconds: float = 1800,
) -> list[AreaVisit]:
    if len(session.visits) <= 1:
        return []

    split_index = 0
    for index in range(1, len(session.visits)):
        gap = (session.visits[index].timestamp - session.visits[index - 1].timestamp).total_seconds()
        if gap >= idle_seconds:
            split_index = index
    if split_index <= 0:
        return []

    trailing = session.visits[split_index:]
    session.visits = session.visits[:split_index]
    _session_time_bounds(session)
    return trailing


def _finalize_session(sessions: list[LogRunSession], current: LogRunSession | None) -> LogRunSession | None:
    if current and current.visits:
        sessions.append(current)
    return None


def _rebuild_chapters(session: LogRunSession) -> None:
    chapters: list[str] = []
    for visit in session.visits:
        if visit.chapter and visit.chapter not in chapters:
            chapters.append(visit.chapter)
    session.chapters = chapters


def _switch_character(
    sessions: list[LogRunSession],
    current: LogRunSession,
    new_character: str,
) -> LogRunSession:
    trailing = _split_trailing_visits_after_idle(current)
    _finalize_session(sessions, current)
    new_session = _start_new_session(sessions, character=new_character)
    if trailing:
        new_session.visits = trailing
        _session_time_bounds(new_session)
        _rebuild_chapters(new_session)
    return new_session


def _read_file_lines(
    path: Path,
    *,
    tail_only: bool = False,
    tail_bytes: int = 16 * 1024 * 1024,
) -> list[str]:
    if not tail_only:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()

    size = path.stat().st_size
    read_size = min(size, tail_bytes)
    with path.open("rb") as handle:
        handle.seek(max(0, size - read_size))
        data = handle.read(read_size)
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if size > read_size and lines:
        lines = lines[1:]

    marker = "***** LOG FILE OPENING *****"
    for index, line in enumerate(lines):
        if marker in line:
            return lines[index:]
    return lines


def analyze_client_log(
    path: Path,
    min_nodes: int = 5,
    locale: str = "zh_tw",
    game_id: str | None = "poe2",
    area_registry: AreaRegistry | None = None,
    chapters_filter: set[str] | None = None,
    max_sessions: int | None = None,
    tail_bytes: int = 16 * 1024 * 1024,
) -> list[LogRunSession]:
    profile = get_game(game_id)
    skip_names = set(profile.skip_area_names)
    chapter_names = set(profile.chapter_names)

    lines = _read_file_lines(path, tail_only=max_sessions is not None, tail_bytes=tail_bytes)
    sessions: list[LogRunSession] = []
    current: LogRunSession | None = None
    current_chapter = ""
    # 待消费的 area id（Generating level ... area "X_Y"）。
    # 消费式配对：一次 Generating 只对应随后的**第一个**真实区域进入事件。
    # 之前用「最近一次 Generating 覆盖」，导致回城时 area_id 串位
    # （实测 The Twilight Strand 拿到了上一个区域的 1_4_3_3）。
    pending_area_id = ""
    # 当前这批 Generating 的真实区域名是否已取过（一批只算一个区域）
    scene_consumed = False
    # 本行所属的 client 进程号：99999 等非主进程会写入与玩家无关的场景名
    line_client_id = ""

    for line in lines:
        if profile.log_open_marker in line:
            current = _finalize_session(sessions, current)
            current = _start_new_session(sessions)
            current_chapter = ""
            pending_area_id = ""
            scene_consumed = False
            line_client_id = ""
            continue

        if line.startswith("#"):
            continue

        if current is None:
            continue

        client_match = CLIENT_ID_RE.search(line)
        if client_match:
            line_client_id = client_match.group(1)

        # 非游戏主进程（99999）：只写 [SCENE] Set Source，从不写 Generating /
        # You have entered。这些场景名（幕間章 / 藏身處：殞落 …）与玩家无关，
        # 直接整行忽略，否则会污染出「幕間章」这种节点。
        if line_client_id in FOREIGN_CLIENT_IDS:
            continue

        generating = GENERATING_AREA_RE.search(line)
        if generating:
            pending_area_id = generating.group(1).strip()
            scene_consumed = False

        timestamp = parse_timestamp(line)
        if timestamp is None:
            continue

        scene_chapter = SCENE_RE.search(line)
        if scene_chapter:
            raw_name = scene_chapter.group(1).strip()
            if game_id == "poe2" or game_id is None:
                from .chapter_normalize import normalize_poe2_chapter

                name = normalize_poe2_chapter(raw_name)
            elif raw_name in chapter_names:
                name = raw_name
            else:
                name = None
            if name:
                current_chapter = name
                if name not in current.chapters:
                    current.chapters.append(name)
                continue
            if raw_name in chapter_names:
                continue
            # 一批 Generating 只对应**一个**真实区域 = 该批第一个非 null 的 Set Source。
            # 实测形态（PoE2）：
            #   GEN:P2_1 | SCENE:(null) | SCENE:卡里交匯道 | SCENE:幕間章 | SCENE:(null) | ...
            # 「幕間章」是章节过场 UI 场景，不是玩家进入的区域；
            # 重复的 (null)/真名 也是同一批的回流。都不是新区域。
            if not pending_area_id or scene_consumed:
                continue
            if raw_name in ("(null)", "(unknown)"):
                continue
            scene_consumed = True

        character_name = _extract_character_name(line)
        if character_name:
            if current.character and character_name != current.character:
                current = _switch_character(sessions, current, character_name)
            elif not current.character:
                current.character = character_name

        if DEATH_CN_RE.search(line) or DEATH_EN_RE.search(line):
            current.deaths += 1

        area = extract_area(line, skip_names, chapter_names)
        if area is None:
            continue

        if current.visits and current.visits[-1].area == area:
            continue

        # 区域进入事件消费掉待配对的 area id（生成即消费，之后回城不再复用）
        area_id = pending_area_id
        pending_area_id = ""
        scene_consumed = True

        current.visits.append(
            AreaVisit(
                area=area,
                timestamp=timestamp,
                chapter=current_chapter,
                area_id=area_id,
            )
        )
        if current.started_at is None:
            current.started_at = timestamp
        current.ended_at = timestamp

    current = _finalize_session(sessions, current)

    for session in sessions:
        _rebuild_chapters(session)

    filtered = [
        session
        for session in sessions
        if len(session.build_splits(locale, area_registry, chapters_filter)) >= min_nodes
    ]
    if max_sessions is not None and len(filtered) > max_sessions:
        filtered = filtered[-max_sessions:]
    return filtered


def format_duration(seconds: float) -> str:
    total = int(max(0, seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
