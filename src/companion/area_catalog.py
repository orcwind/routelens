from __future__ import annotations

TOWN_NAMES = {
    "皆伐營地",
    "Clearfell Encampment",
    "阿杜拉車隊",
    "Adura's Caravan",
    "高地神塔營地",
    "Ziggurat Encampment",
    "庇護所",
    "金司馬區",
    "Kingsmarch",
}

TOWN_KEYWORDS = ("營地", "車隊", "庇護所", "郊區", "神塔營地", "藏身處", "Encampment", "Caravan", "Outskirts")

TW_TO_EN: dict[str, str] = {
    "河岸": "The Riverbank",
    "皆伐營地": "Clearfell Encampment",
    "皆伐": "Clearfell",
    "葛瑞爾林": "The Grelwood",
    "赤谷": "The Red Vale",
    "纏縛陰林": "The Grim Tangle",
    "不朽帝國之墓": "Cemetery of the Eternals",
    "配偶的墓室": "Tomb of the Consort",
    "政務官陵墓": "Mausoleum of the Praetor",
    "獵場": "Hunting Grounds",
    "弗雷索恩": "Freythorn",
    "奧格姆農地": "Ogham Farmlands",
    "奧格姆村": "Ogham Village",
    "宅第壁壘": "The Manor Ramparts",
    "奧格姆宅第": "Ogham Manor",
    "瓦斯提里郊區": "Vastiri Outskirts",
    "阿杜拉車隊": "Adura's Caravan",
    "哈拉妮關口": "Halani Gates",
    "莫頓挖石場": "Morden Quarry",
    "莫頓礦坑": "Morden Mine",
    "叛徒之路": "Traitor's Pass",
    "乳齒象惡地": "Mammoth Badlands",
    "骨坑": "The Bone Pits",
    "凱斯城": "Qimah",
    "失落之城": "The Lost City",
    "掩埋神殿": "Buried Shrine",
    "泰坦之谷": "Valley of the Titans",
    "泰坦石窟": "Titan Grotto",
    "戴斯哈": "Deshar",
    "悼念之路": "Path of Mourning",
    "戴斯哈尖塔": "Deshar Spire",
    "無畏隊": "The Dreadnought",
    "風沙沼澤": "Sandswept Marsh",
    "高地神塔營地": "Ziggurat Encampment",
    "叢林遺跡": "Jungle Ruins",
    "劇毒墓穴": "Venomous Vault",
    "感染荒地": "Blighted Wasteland",
    "神祕避難所": "Mystic Refuge",
    "龍蜥濕地": "Drake Wetlands",
    "吉卡尼的機械迷城": "Jiquani's Mechanical Metropolis",
    "吉卡尼的聖域": "Jiquani's Sanctum",
    "瑪特蘭水道": "Matlan Waterways",
    "阿札克泥沼": "Azak Bog",
    "淹沒之城": "Sunken City",
    "熔岩寶庫": "Molten Vault",
    "污垢頂峰": "Peak of Filth",
    "科佩克神殿": "Temple of Kopec",
    "奧札爾": "Ogham Farmlands",
    "阿戈拉": "Agora",
    "漆黑密室": "Chamber of Darkness",
    "金司馬區": "Kingsmarch",
    "凱吉灣": "Keth Bay",
    "旅程之末": "Journey's End",
    "伯勞鳥之島": "Shrike Island",
    "尼加卡努": "Ngakanu",
    "瓦卡帕努島": "Wakapu Island",
    "吟謠洞窟": "Singing Caverns",
    "悉妮蔻拉之眼": "Eye of Synckra",
    "亡者之殿": "Hall of the Dead",
    "祖靈的試煉": "Trial of the Ancestors",
    "金氏島": "Kin Island",
    "火山迷窟": "Volcanic Caverns",
    "廢棄監獄": "Abandoned Prison",
    "單獨禁閉室": "Solitary Confinement",
    "阿拉塔斯": "Ararat",
    "挖掘": "The Excavation",
    "無盡深淵": "Endless Abyss",
    "部族之心": "Heart of the Tribe",
    "林間空地": "Forest Clearing",
    "灰燼森林": "Ashen Forest",
    "庫萊亞村": "Kuleya Village",
    "冰川湖泊": "Glacial Lake",
    "庫萊亞山巔": "Kuleya Peak",
    "瓦爾遺跡": "Vaal Ruins",
    "阿茲里的神廟": "Temple of Atziri",
    "蝕刻溪谷": "Etched Ravine",
    "庫阿西克寶庫": "Kuahsiq Vault",
    "狂嗥洞穴": "Howling Caves",
}

EN_TO_TW = {value: key for key, value in TW_TO_EN.items()}

SKIP_AREA_NAMES = {"(null)", "(unknown)"}
CHAPTER_NAMES = {"第一章", "第二章", "第三章", "第四章", "第五章", "第六章"}


def is_town(area: str) -> bool:
    if area in TOWN_NAMES:
        return True
    return any(keyword in area for keyword in TOWN_KEYWORDS)


def to_english(area: str) -> str:
    if area in TW_TO_EN:
        return TW_TO_EN[area]
    if area in EN_TO_TW:
        return area
    return area


def to_display(area: str, locale: str = "zh_tw") -> str:
    if locale == "en":
        return to_english(area)
    if area in EN_TO_TW:
        return EN_TO_TW[area]
    return area
