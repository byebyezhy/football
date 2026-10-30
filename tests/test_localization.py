"""Keep display names separate from canonical soccerdata match identifiers."""

import unittest

from football_predictor.web.team_names import TEAM_NAMES_ZH, competition_labels, team_labels


class TeamLocalizationTests(unittest.TestCase):
    def test_all_recent_six_seasons_new_leagues_have_chinese_team_labels(self):
        # Names were checked against the official Football-Data six-season CSVs.
        expected = {
            "ESP-La Liga": "Alaves|Almeria|Ath Bilbao|Ath Madrid|Barcelona|Betis|Cadiz|Celta|Elche|Espanol|Getafe|Girona|Granada|La Coruna|Las Palmas|Leganes|Levante|Malaga|Mallorca|Osasuna|Oviedo|Real Madrid|Santander|Sevilla|Sociedad|Valencia|Valladolid|Vallecano|Villarreal",
            "GER-Bundesliga": "Augsburg|Bayern Munich|Bielefeld|Bochum|Darmstadt|Dortmund|Ein Frankfurt|Elversberg|FC Koln|Freiburg|Greuther Furth|Hamburg|Heidenheim|Hertha|Hoffenheim|Holstein Kiel|Leverkusen|M'gladbach|Mainz|Paderborn|RB Leipzig|Schalke 04|St Pauli|Stuttgart|Union Berlin|Werder Bremen|Wolfsburg",
            "ITA-Serie A": "Atalanta|Bologna|Cagliari|Como|Cremonese|Empoli|Fiorentina|Frosinone|Genoa|Inter|Juventus|Lazio|Lecce|Milan|Monza|Napoli|Parma|Pisa|Roma|Salernitana|Sampdoria|Sassuolo|Spezia|Torino|Udinese|Venezia|Verona",
            "FRA-Ligue 1": "Ajaccio|Angers|Auxerre|Bordeaux|Brest|Clermont|Le Havre|Le Mans|Lens|Lille|Lorient|Lyon|Marseille|Metz|Monaco|Montpellier|Nantes|Nice|Paris FC|Paris SG|Reims|Rennes|St Etienne|Strasbourg|Toulouse|Troyes",
        }
        for competition, source_names in expected.items():
            with self.subTest(competition=competition):
                names = source_names.split("|")
                self.assertEqual(set(TEAM_NAMES_ZH[competition]), set(names))
                translated = team_labels(competition, names)
                self.assertTrue(all(translated[name] != name for name in names))
                self.assertTrue(all(any(ord(c) > 127 for c in translated[name])
                                    for name in names))

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
