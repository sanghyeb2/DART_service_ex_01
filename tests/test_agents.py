import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from agent_client import AgentError, run_agent
from business_agent import analyze_business
from tech_agent import analyze_technology_and_investment
from insight_agent import generate_insight
from config import Settings
from schemas import BusinessResult, TechResult, InsightResult


class AgentTests(unittest.TestCase):
    def setUp(self):
        config = patch('config.Settings.from_env', return_value=Settings())
        config.start()
        self.addCleanup(config.stop)

    def test_mock_pipeline_has_schemas_and_no_network(self):
        with patch('requests.sessions.Session.request', side_effect=AssertionError('network')):
            business = analyze_business('===== PAGE 2 =====\n사업의 내용')
            tech = analyze_technology_and_investment('===== PAGE 3 =====\n연구개발')
            insight = generate_insight(business, tech)
        self.assertEqual(set(business), set(BusinessResult.model_fields))
        self.assertEqual(set(tech), set(TechResult.model_fields))
        self.assertEqual(set(insight), set(InsightResult.model_fields))
        self.assertIn('가상', business['company_name'])
        self.assertTrue(insight['job_insights'][0]['evidence'])

    def test_results_are_independent_copies(self):
        first = analyze_business('one')
        first['major_products'].append('contamination')
        self.assertNotIn('contamination', analyze_business('two')['major_products'])

    def test_insight_uses_only_two_jsons_and_handles_absent_facts(self):
        business = BusinessResult().model_dump()
        tech = TechResult().model_dump()
        insight = generate_insight(business, tech)
        self.assertEqual(insight['job_insights'], [])
        self.assertEqual(insight['investment_direction'], [])
        self.assertIn('확인되지 않음', insight['summary'])

    def test_schema_rejects_wrong_lists_and_unknown_fields(self):
        for value in ('oops', {}, 3):
            with self.assertRaises(ValidationError):
                BusinessResult.model_validate({'market_conditions': value})
        with self.assertRaises(ValidationError):
            TechResult.model_validate({'rd_projects': [{'source_page': -1}]})
        with self.assertRaises(ValidationError):
            BusinessResult.model_validate({'hallucinated': 'value'})

    def test_live_wrapper_sends_only_two_jsons(self):
        settings = Settings(use_mock=False, insight_agent_id='insight')
        with patch('config.Settings.from_env', return_value=settings), \
             patch('insight_agent.run_agent_with_json', return_value={}) as client:
            business, tech = BusinessResult().model_dump(), TechResult().model_dump()
            generate_insight(business, tech)
        client.assert_called_once_with('insight', {
            'business': business, 'technology_and_investment': tech,
        })

    def test_live_mode_fails_closed_with_friendly_message(self):
        with patch('config.Settings.from_env', return_value=Settings(use_mock=False)):
            with self.assertRaisesRegex(AgentError, 'UPSTAGE_API_KEY'):
                run_agent('', 'text')
        configured = Settings(use_mock=False, upstage_api_key='placeholder',
                              upstage_agent_api_url='https://example.invalid/agents')
        with patch('config.Settings.from_env', return_value=configured), \
             patch('requests.sessions.Session.request', side_effect=AssertionError('network')):
            with self.assertRaisesRegex(AgentError, 'Phase 3'):
                run_agent('example', 'text')


class ConfigTests(unittest.TestCase):
    def test_defaults_and_new_environment_names(self):
        with patch('config.load_dotenv'), patch.dict(os.environ, {}, clear=True):
            self.assertTrue(Settings.from_env().use_mock)
        with patch('config.load_dotenv'), patch.dict(os.environ, {
            'USE_MOCK': 'false', 'BUSINESS_AGENT_ID': 'business', 'TECH_AGENT_ID': 'tech',
            'INSIGHT_AGENT_ID': 'insight', 'UPSTAGE_AGENT_API_URL': 'https://example.invalid',
        }, clear=True):
            config = Settings.from_env()
        self.assertFalse(config.use_mock)
        self.assertEqual(config.business_agent_id, 'business')

    def test_invalid_mode_is_not_silently_live(self):
        with patch('config.load_dotenv'), patch.dict(os.environ, {'USE_MOCK': 'typo'}):
            with self.assertRaisesRegex(ValueError, 'USE_MOCK'):
                Settings.from_env()
