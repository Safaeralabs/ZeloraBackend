from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ai_engine.sales_models import BuyerProfile, SalesContext
from apps.ai_engine.sales_reply import _apply_quality_gate


class SalesReplyQualityGateTests(SimpleTestCase):
    def setUp(self):
        self.buyer = BuyerProfile()
        self.sales_ctx = SalesContext()
        self.settings = MagicMock()
        self.conversation = MagicMock()
        self.conversation.metadata = {}

    @patch('apps.ai_engine.sales_evaluator.evaluate_reply')
    def test_send_action_keeps_reply(self, mock_evaluate):
        mock_evaluate.return_value = {
            'score': 0.82,
            'flags': [],
            'action': 'send',
            'feedback': 'ok',
        }
        reply = _apply_quality_gate(
            reply='Respuesta original',
            stage='considering',
            buyer=self.buyer,
            sales_ctx=self.sales_ctx,
            channel='web',
            settings=self.settings,
            conversation=self.conversation,
            products=[],
        )
        self.assertEqual(reply, 'Respuesta original')
        self.assertEqual(self.conversation.metadata['last_evaluation']['action'], 'send')

    @patch('apps.ai_engine.sales_reply._human_rewrite_reply')
    @patch('apps.ai_engine.sales_evaluator.evaluate_reply')
    def test_rewrite_action_rewrites_and_sends(self, mock_evaluate, mock_rewrite):
        mock_evaluate.side_effect = [
            {'score': 0.55, 'flags': ['generic'], 'action': 'rewrite', 'feedback': 'make it specific'},
            {'score': 0.78, 'flags': [], 'action': 'send', 'feedback': 'better'},
        ]
        mock_rewrite.return_value = 'Respuesta reescrita'

        reply = _apply_quality_gate(
            reply='Respuesta original',
            stage='considering',
            buyer=self.buyer,
            sales_ctx=self.sales_ctx,
            channel='web',
            settings=self.settings,
            conversation=self.conversation,
            products=[],
        )
        self.assertEqual(reply, 'Respuesta reescrita')
        self.assertEqual(self.conversation.metadata['last_evaluation']['action'], 'send')

    @patch('apps.ai_engine.sales_reply._escalation_reply', return_value='ESCALATE')
    @patch('apps.ai_engine.sales_reply._human_rewrite_reply', return_value=None)
    @patch('apps.ai_engine.sales_evaluator.evaluate_reply')
    def test_rewrite_failure_escalates(self, mock_evaluate, _mock_rewrite, _mock_escalation):
        mock_evaluate.return_value = {
            'score': 0.45,
            'flags': ['generic'],
            'action': 'rewrite',
            'feedback': 'rewrite',
        }

        reply = _apply_quality_gate(
            reply='Respuesta original',
            stage='considering',
            buyer=self.buyer,
            sales_ctx=self.sales_ctx,
            channel='web',
            settings=self.settings,
            conversation=self.conversation,
            products=[],
        )
        self.assertEqual(reply, 'ESCALATE')
        self.assertEqual(self.conversation.metadata['last_evaluation']['action'], 'escalate')
        self.assertIn('rewrite_failed', self.conversation.metadata['last_evaluation']['flags'])

    @patch('apps.ai_engine.sales_reply._escalation_reply', return_value='ESCALATE')
    @patch('apps.ai_engine.sales_evaluator.evaluate_reply')
    def test_escalate_action_returns_handoff_reply(self, mock_evaluate, _mock_escalation):
        mock_evaluate.return_value = {
            'score': 0.2,
            'flags': ['forbidden_claim'],
            'action': 'escalate',
            'feedback': 'unsafe',
        }
        reply = _apply_quality_gate(
            reply='Respuesta original',
            stage='checkout_blocked',
            buyer=self.buyer,
            sales_ctx=self.sales_ctx,
            channel='whatsapp',
            settings=self.settings,
            conversation=self.conversation,
            products=[],
        )
        self.assertEqual(reply, 'ESCALATE')
        self.assertEqual(self.conversation.metadata['last_evaluation']['action'], 'escalate')
