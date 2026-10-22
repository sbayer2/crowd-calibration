"""nba_free.py's matching and schedule rules, offline. Standard library only: python -m unittest tests.test_nba_free"""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nba_free as N  # noqa: E402

UTC = dt.timezone.utc


def game(gid: str, start: str, away: str = "Sacramento Kings", home: str = "LA Clippers") -> dict:
    t = N.iso(start)
    return {"id": gid, "away": away, "home": home, "start": start, "day": t.astimezone(N.CT).date().isoformat(),
            "status": "STATUS_SCHEDULED"}


class Schedule(unittest.TestCase):
    def test_start_moves_only_before_tipoff(self):
        games = {"1": {**game("1", "2026-10-22T23:00:00Z"), "listed_at": "x"}}
        N.merge_schedule(games, [game("1", "2026-10-22T23:30:00Z")], dt.datetime(2026, 10, 22, 20, tzinfo=UTC))
        self.assertEqual(games["1"]["start"], "2026-10-22T23:30:00Z")
        self.assertEqual(len(games["1"]["moves"]), 1)
        N.merge_schedule(games, [game("1", "2026-10-22T23:41:00Z")], dt.datetime(2026, 10, 22, 23, 35, tzinfo=UTC))
        self.assertEqual(games["1"]["start"], "2026-10-22T23:30:00Z")             # read after the start: kept

    def test_late_tipoff_keeps_its_central_day(self):
        self.assertEqual(game("1", "2026-10-23T03:30:00Z")["day"], "2026-10-22")


class Names(unittest.TestCase):
    def test_polymarket_nicknames(self):
        self.assertTrue(N.team_in("76ers", "Philadelphia 76ers"))
        self.assertTrue(N.team_in("Trail Blazers", "Portland Trail Blazers"))
        self.assertFalse(N.team_in("Nets", "Brooklyn Netsx"))

    def test_kalshi_cities(self):
        self.assertTrue(N.kalshi_team("Los Angeles C", "LA Clippers"))
        self.assertFalse(N.kalshi_team("Los Angeles C", "Los Angeles Lakers"))
        self.assertTrue(N.kalshi_team("Los Angeles L", "Los Angeles Lakers"))
        self.assertTrue(N.kalshi_team("Golden State", "Golden State Warriors"))
        self.assertTrue(N.kalshi_team("New York", "New York Knicks"))
        self.assertFalse(N.kalshi_team("New Orleans", "New York Knicks"))

    def test_kalshi_rules_and_match(self):
        rules = ("If Sacramento wins the Sacramento vs Los Angeles C Pro Basketball game originally scheduled for "
                 "Oct 21, 2026, then the market resolves to Yes.")
        self.assertEqual(N.kalshi_game(rules), ("Sacramento", "Los Angeles C", dt.date(2026, 10, 21)))
        events = {"E1": [{"rules_primary": rules}],
                  "E2": [{"rules_primary": rules.replace("Oct 21", "Nov 30")}],                    # rematch, other date
                  "E3": [{"rules_primary": rules.replace("Los Angeles C", "Los Angeles L")}]}      # other LA team
        self.assertEqual(N.kalshi_match(game("1", "2026-10-22T02:30:00Z"), events), ["E1"])


class Settled(unittest.TestCase):
    def test_needs_espn_polymarket_and_kalshi(self):
        r = {"espn": {"completed": True}, "poly": {"away_won": 0}, "kalshi": {"away_result": "no"}}
        self.assertTrue(N.settled(r))
        self.assertFalse(N.settled({**r, "kalshi": {"away_result": None}}))           # Kalshi not settled yet: retry
        self.assertTrue(N.settled({**r, "kalshi": {"match": "0 candidates"}}))        # no Kalshi game: nothing to wait for
        self.assertFalse(N.settled({**r, "poly": {"away_won": None}}))


if __name__ == "__main__":
    unittest.main()
