from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ai_router.executors.route_to_agent import RouteToAgentExecutor


class RouteToAgentExecutorLogTests(SimpleTestCase):
    @patch('apps.ai_engine.models.SalesAgentLog.objects.create')
    def test_persist_sales_log_includes_evaluation_and_channel(self, mock_create):
        executor = RouteToAgentExecutor(agent_type='sales')
        result = SimpleNamespace(
            stage='considering',
            confidence=0.87,
            decision='recommend',
            handoff=SimpleNamespace(needed=False, reason=''),
            products_shown=[{'id': 'p1'}],
            recommended_actions=[SimpleNamespace(to_dict=lambda: {'type': 'suggest_product'})],
            context_used={'products_found': 1},
        )
        conversation = MagicMock()
        conversation.metadata = {
            'last_evaluation': {
                'score': 0.82,
                'flags': ['no_cta'],
                'action': 'rewrite',
                'coherencia': 0.9,
                'naturalidad': 0.8,
                'brand_fit': 0.7,
                'cta_quality': 0.6,
            }
        }
        conversation.canal = 'whatsapp'
        organization = MagicMock()

        executor._persist_sales_log(result, conversation, organization)

        _, kwargs = mock_create.call_args
        assert kwargs['evaluation_score'] == 0.82
        assert kwargs['evaluation_flags'] == ['no_cta']
        assert kwargs['evaluation_coherencia'] == 0.9
        assert kwargs['evaluation_naturalidad'] == 0.8
        assert kwargs['evaluation_brand_fit'] == 0.7
        assert kwargs['evaluation_cta_quality'] == 0.6
        assert kwargs['channel'] == 'whatsapp'
