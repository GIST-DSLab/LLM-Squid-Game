"""Behavior tests for false-completion rejection; fixtures are not arena evidence."""
import copy
import tempfile
import unittest
from pathlib import Path
from check_rubric import GOALS, check, sha256


class RubricGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'rubric.md').write_text('Test rubric, not research evidence')
        (self.root / 'design.md').write_text('Test design, not research evidence')
        self.report = {
            'gate': 'DESIGN_ACCEPTED', 'rubric_sha256': sha256(self.root / 'rubric.md'),
            'verdict': 'PASS', 'unresolved_critical': [],
            'author': {'profile': 'writer', 'session_id': 'writer-session'},
            'reviewer': {'profile': 'reviewer', 'session_id': 'reviewer-session'},
            'artifacts': [{'path': 'design.md', 'sha256': sha256(self.root / 'design.md')}],
            'goals': [{'id': gid, 'D': 2 if gid != 'G12' else 'N/A', 'E': 'U',
                       'D_evidence': [{'path': 'design.md', 'locator': gid}],
                       'note': 'Fixture: design only; empirical work not run'} for gid in GOALS],
        }

    def test_design_does_not_require_unrun_empirical_claims(self):
        self.assertEqual(check(self.report, self.root, 'DESIGN_ACCEPTED'), [])

    def test_unmet_or_unknown_required_goal_fails(self):
        for value in [0, 1, 'U', 'N/A', True, 2.0]:
            with self.subTest(score=value):
                r = copy.deepcopy(self.report); r['goals'][0]['D'] = value
                self.assertTrue(check(r, self.root, 'DESIGN_ACCEPTED'))

    def test_missing_or_duplicate_goal_fails(self):
        for rows in [self.report['goals'][:-1], self.report['goals'] + [self.report['goals'][0]]]:
            r = copy.deepcopy(self.report); r['goals'] = rows
            self.assertTrue(check(r, self.root, 'DESIGN_ACCEPTED'))

    def test_stale_rubric_fails(self):
        (self.root / 'rubric.md').write_text('Changed criterion')
        self.assertTrue(check(self.report, self.root, 'DESIGN_ACCEPTED'))

    def test_stale_final_artifact_fails(self):
        (self.root / 'design.md').write_text('Changed final design')
        self.assertTrue(check(self.report, self.root, 'DESIGN_ACCEPTED'))

    def test_self_review_fails(self):
        self.report['reviewer'] = self.report['author'].copy()
        self.assertTrue(check(self.report, self.root, 'DESIGN_ACCEPTED'))

    def test_critical_or_revise_verdict_fails(self):
        for key, value in [('unresolved_critical', ['G01 idle policy']), ('verdict', 'REVISE')]:
            r = copy.deepcopy(self.report); r[key] = value
            self.assertTrue(check(r, self.root, 'DESIGN_ACCEPTED'))

    def test_unbound_evidence_fails(self):
        self.report['goals'][0]['D_evidence'] = [{'path': 'imaginary.md', 'locator': '1'}]
        self.assertTrue(check(self.report, self.root, 'DESIGN_ACCEPTED'))

    def test_design_cannot_claim_release(self):
        self.report['gate'] = 'RELEASE_READY'
        self.assertTrue(check(self.report, self.root, 'RELEASE_READY'))

    def test_different_requested_gate_fails(self):
        self.assertTrue(check(self.report, self.root, 'ARENA_VALIDATED'))


if __name__ == '__main__':
    unittest.main()
