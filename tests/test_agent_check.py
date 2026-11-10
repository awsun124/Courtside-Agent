"""Check the small agent evaluation without external services."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from courtside.investigation import EvidenceTools
from scripts.check_agent import assess, run_check, scenario


class AgentCheckTests(unittest.TestCase):
    def test_offline_case_finds_related_rumor_without_citing_it(self):
        result, briefing = scenario()
        target = briefing['candidates'][0]
        tools = EvidenceTools(result, briefing, [])
        related = tools.inspect_related_stories(target['id'])['related']
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]['event'], 'trade')
        self.assertTrue(next(story for story in result['stories'] if story['event'] == 'trade')['has_rumor'])
        with patch('subprocess.run', side_effect=AssertionError('No network allowed')):
            report = run_check()
        self.assertTrue(report['passed'])
        self.assertEqual(report['investigation']['llm_calls'], 0)
        self.assertTrue(all('charlie.example.com' not in citation['url'] for citation in report['target']['summary']['citations']))

    def test_evaluation_rejects_a_citation_from_the_related_rumor(self):
        report = run_check()
        before = deepcopy(report['target'])
        report['target']['summary']['citations'][0]['url'] = 'https://charlie.example.com/sample/reed'
        evaluated = assess(before, {'candidates': [report['target']], 'investigation': report['investigation']})
        self.assertFalse(evaluated['passed'])
        self.assertFalse(evaluated['checks']['cited_target'])

    def test_a_valid_investigation_can_skip_redundant_search(self):
        report = run_check()
        target = report['target']
        target['investigation']['activity'] = [step for step in target['investigation']['activity'] if step['tool'] != 'search_articles']
        evaluated = assess(deepcopy(target), {'candidates': [target], 'investigation': report['investigation']})
        self.assertTrue(evaluated['passed'])
        self.assertFalse(evaluated['optional_checks']['searched_articles'])

    def test_live_mode_requires_opt_in_and_does_not_silently_run_rules(self):
        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / '.env'
            env_file.write_text('ENABLE_LLM_CALLS=false\nLLM_API_KEY=fake-key\nLLM_MODEL=test-model\n')
            with patch.dict('os.environ', {}, clear=True), patch('subprocess.run') as network:
                with self.assertRaises(ValueError):
                    run_check(live=True, env_file=env_file)
            network.assert_not_called()


if __name__ == '__main__':
    unittest.main()
