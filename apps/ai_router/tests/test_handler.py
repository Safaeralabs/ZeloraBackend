from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ai_router.handler import handle_inbound_message
from apps.ai_router.schemas import RouteType


class AIRouterHandlerTests(SimpleTestCase):
    @patch('apps.ai_router.handler._persist_decision')
    @patch('apps.ai_router.handler.build_ai_router_service')
    @patch('apps.ai_router.handler._execute_decision')
    def test_does_not_auto_reply_when_conversation_is_human_owned(self, mock_execute, mock_build_router, _mock_persist) -> None:
        decision = MagicMock()
        decision.intent = 'buy_intent'
        decision.sentiment = 'positive'
        decision.route = RouteType.ROUTE_TO_SALES_AGENT
        decision.to_dict.return_value = {}

        router = MagicMock()
        router.route.return_value = decision
        mock_build_router.return_value = router

        conversation = MagicMock()
        conversation.id = 'conv-1'
        conversation.canal = 'app'
        conversation.contact_id = 'contact-1'
        conversation.metadata = {'operator_state': {'owner': 'humano'}}
        conversation.sentimiento = 'neutro'

        message = MagicMock()
        message.content = 'Quiero comprar'

        organization = MagicMock()
        organization.id = 'org-1'

        reply, returned_decision = handle_inbound_message(
            conversation=conversation,
            message=message,
            organization=organization,
        )

        self.assertIsNone(reply)
        self.assertEqual(returned_decision, decision)
        mock_execute.assert_not_called()
