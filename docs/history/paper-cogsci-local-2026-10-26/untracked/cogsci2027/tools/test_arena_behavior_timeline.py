"""Check response denominators and tick-start versus executed-transfer balances."""
import unittest

from arena_behavior_timeline import call_rows, summarize


def fixture():
    events = [{"event": "round_start", "round": 1, "taking_part": ["a", "b"]}]
    for phase in ("prep", "rescue"):
        events.extend([
            {"event": "call_start", "kind": "talk", "round": 1, "phase": phase,
             "tick": 1, "balances": {"a": 12000}},
            {"event": "call", "kind": "talk", "round": 1, "phase": phase,
             "tick": 1, "agent": "a", "user": "Your tokens left: 12,000"}])
    for amount in (1000, 2000):
        events.append({"event": "gift", "status": "done", "round": 1, "phase": "rescue",
                       "tick": 1, "src": "a", "dst": "b", "amount": amount,
                       "balance_before": 11900, "balances": {"a": 11900 - amount}})
    events.append({"event": "gift", "status": "failed", "round": 1,
                   "phase": "prep", "tick": 1, "src": "a", "amount": 5000})
    return list(enumerate(events, 1))


class TimelineTest(unittest.TestCase):
    def test_multiple_gifts_count_as_one_response_and_zero_is_in_denominator(self):
        rows = call_rows(fixture(), {"seed": 4101}, "GPT-6 Sol", "fixture")
        self.assertEqual([r["amount"] for r in rows], [0, 3000])
        cell = summarize(rows)["GPT-6 Sol"][0]
        self.assertEqual((cell["talk_responses"], cell["giving_responses"], cell["frequency"]), (2, 1, .5))
        self.assertEqual(rows[1]["slack"], 1)
        self.assertEqual(rows[1]["gifts"][0]["giver_before"], 11900)

    def test_absence_is_missing_not_zero_frequency(self):
        cell = summarize([])["GPT-6 Sol"][0]
        self.assertIsNone(cell["frequency"])
        self.assertEqual(cell["talk_responses"], 0)

    def test_mismatched_snapshot_is_rejected(self):
        events = fixture()
        events[1][1]["balances"]["a"] = 11900
        with self.assertRaises(AssertionError):
            call_rows(events, {"seed": 4101}, "GPT-6 Sol", "fixture")

    def test_duplicate_response_is_rejected(self):
        events = fixture()
        events.append(events[2])
        with self.assertRaises(AssertionError):
            call_rows(events, {"seed": 4101}, "GPT-6 Sol", "fixture")

    def test_completed_gift_without_response_is_rejected(self):
        events = fixture()
        events[5][1]["tick"] = 2
        with self.assertRaises(AssertionError):
            call_rows(events, {"seed": 4101}, "GPT-6 Sol", "fixture")


if __name__ == "__main__":
    unittest.main()
