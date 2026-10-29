"""Keep display names separate from canonical soccerdata match identifiers."""

import unittest

from football_predictor.web.team_names import competition_labels, team_labels


class TeamLocalizationTests(unittest.TestCase):
    def test_all_2024_25_premier_league_teams_have_verified_labels(self):
        names = {
            "Arsenal": "阿森纳",
            "Aston Villa": "阿斯顿维拉",
            "Bournemouth": "伯恩茅斯",
            "Brentford": "布伦特福德",
            "Brighton": "布莱顿",
            "Chelsea": "切尔西",
            "Crystal Palace": "水晶宫",
            "Everton": "埃弗顿",
            "Fulham": "富勒姆",
            "Ipswich": "伊普斯维奇",
            "Leicester": "莱斯特城",
            "Liverpool": "利物浦",
            "Man City": "曼城",
            "Man United": "曼联",
            "Newcastle": "纽卡斯尔联",
            "Nott'm Forest": "诺丁汉森林",
            "Southampton": "南安普顿",
            "Tottenham": "热刺",
            "West Ham": "西汉姆联",
            "Wolves": "狼队",
        }
        self.assertEqual(team_labels("ENG-Premier League", list(names)), names)

    def test_unmapped_teams_and_competitions_keep_original_identifiers(self):
        self.assertEqual(team_labels("ENG-Premier League", ["New Club"]),
                         {"New Club": "New Club"})
        self.assertEqual(team_labels("OTHER", ["Arsenal"]), {"Arsenal": "Arsenal"})
        self.assertEqual(competition_labels(["ENG-Premier League", "OTHER"]),
                         {"ENG-Premier League": "英超", "OTHER": "OTHER"})


if __name__ == "__main__":
    unittest.main()
