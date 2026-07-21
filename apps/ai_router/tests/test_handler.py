from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ai_router.handler import _execute_decision, handle_inbound_message
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


class ExecuteDecisionFollowupWiringTests(SimpleTestCase):
    """The order-confirmation followup must surface as its own post_action,
    distinct from (and alongside) bot_message_metadata, so the caller can
    send it as a second proactive chat bubble."""

    @patch('apps.ai_router.handler._sales_agent_enabled', return_value=True)
    @patch('apps.ai_router.handler.SalesAgentExecutor')
    def test_followup_message_becomes_its_own_post_action(self, mock_executor_cls, _mock_enabled):
        executor = MagicMock()
        executor.execute.return_value = 'Listo, tu pedido fue creado.'
        executor.get_message_metadata.return_value = {'ui_payload': {'kind': 'order_confirmed'}}
        executor.get_followup_messages.return_value = [
            {'text': 'Te escribo apenas este listo.', 'kind': 'order_followup'},
        ]
        mock_executor_cls.return_value = executor

        decision = MagicMock()
        decision.route = RouteType.ROUTE_TO_SALES_AGENT
        decision.post_actions = []

        reply = _execute_decision(
            decision=decision, conversation=MagicMock(canal='app'), message=MagicMock(), organization=MagicMock(),
        )

        self.assertEqual(reply, 'Listo, tu pedido fue creado.')
        action_types = [pa['action_type'] for pa in decision.post_actions]
        self.assertIn('bot_message_metadata', action_types)
        self.assertIn('bot_followup_message', action_types)
        followup_action = next(pa for pa in decision.post_actions if pa['action_type'] == 'bot_followup_message')
        self.assertEqual(followup_action['payload']['text'], 'Te escribo apenas este listo.')
        self.assertEqual(followup_action['payload']['kind'], 'order_followup')

    @patch('apps.ai_router.handler._sales_agent_enabled', return_value=True)
    @patch('apps.ai_router.handler.SalesAgentExecutor')
    def test_burst_parts_become_ordered_post_actions(self, mock_executor_cls, _mock_enabled):
        executor = MagicMock()
        executor.execute.return_value = 'Hola'
        executor.get_message_metadata.return_value = {}
        executor.get_followup_messages.return_value = [
            {'text': '35mil', 'kind': 'burst'},
            {'text': 'Que color te gustaria ?', 'kind': 'burst'},
        ]
        mock_executor_cls.return_value = executor

        decision = MagicMock()
        decision.route = RouteType.ROUTE_TO_SALES_AGENT
        decision.post_actions = []

        reply = _execute_decision(
            decision=decision, conversation=MagicMock(canal='app'), message=MagicMock(), organization=MagicMock(),
        )

        self.assertEqual(reply, 'Hola')
        followup_actions = [pa for pa in decision.post_actions if pa['action_type'] == 'bot_followup_message']
        self.assertEqual([pa['payload']['text'] for pa in followup_actions], ['35mil', 'Que color te gustaria ?'])
        self.assertTrue(all(pa['payload']['kind'] == 'burst' for pa in followup_actions))

    @patch('apps.ai_router.handler._sales_agent_enabled', return_value=True)
    @patch('apps.ai_router.handler.SalesAgentExecutor')
    def test_no_followup_post_action_when_executor_has_nothing_to_add(self, mock_executor_cls, _mock_enabled):
        executor = MagicMock()
        executor.execute.return_value = 'Tenemos varias opciones disponibles.'
        executor.get_message_metadata.return_value = {}
        executor.get_followup_messages.return_value = []
        mock_executor_cls.return_value = executor

        decision = MagicMock()
        decision.route = RouteType.ROUTE_TO_SALES_AGENT
        decision.post_actions = []

        _execute_decision(
            decision=decision, conversation=MagicMock(canal='app'), message=MagicMock(), organization=MagicMock(),
        )

        action_types = [pa['action_type'] for pa in decision.post_actions]
        self.assertNotIn('bot_followup_message', action_types)
