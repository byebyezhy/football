"""Localized display labels for teams; never replace canonical source names.

MatchHistory's source names remain the database and prediction API identifiers.
Missing translations fall back to the exact original spelling until a reviewed
mapping is added for the relevant competition.
"""

from __future__ import annotations

COMPETITION_NAMES_ZH = {
    "ENG-Premier League": "英超",
    "ESP-La Liga": "西甲",
    "GER-Bundesliga": "德甲",
    "ITA-Serie A": "意甲",
    "FRA-Ligue 1": "法甲",
}

TEAM_NAMES_ZH = {
    "ENG-Premier League": {
        "Arsenal": "阿森纳",
        "Aston Villa": "阿斯顿维拉",
        "Bournemouth": "伯恩茅斯",
        "Brentford": "布伦特福德",
        "Brighton": "布莱顿",
        "Burnley": "伯恩利",
        "Chelsea": "切尔西",
        "Crystal Palace": "水晶宫",
        "Everton": "埃弗顿",
        "Fulham": "富勒姆",
        "Ipswich": "伊普斯维奇",
        "Leeds": "利兹联",
        "Leicester": "莱斯特城",
        "Liverpool": "利物浦",
        "Luton": "卢顿",
        "Man City": "曼城",
        "Man United": "曼联",
        "Newcastle": "纽卡斯尔联",
        "Norwich": "诺维奇",
        "Nott'm Forest": "诺丁汉森林",
        "Sheffield United": "谢菲尔德联",
        "Southampton": "南安普顿",
        "Sunderland": "桑德兰",
        "Tottenham": "热刺",
        "Watford": "沃特福德",
        "West Brom": "西布朗",
        "West Ham": "西汉姆联",
        "Wolves": "狼队",
    },
}


def competition_labels(competitions: list[str]) -> dict[str, str]:
    """Return translated display labels for the actual available leagues."""
    return {code: COMPETITION_NAMES_ZH.get(code, code) for code in competitions}


def team_labels(competition: str, teams: list[str]) -> dict[str, str]:
    """Keep source identifiers unchanged; labels are solely for presentation."""
    aliases = TEAM_NAMES_ZH.get(competition, {})
    return {team: aliases.get(team, team) for team in teams}
