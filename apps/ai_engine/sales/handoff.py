"""
Handoff Handler — Manages escalation from sales agent to human.
"""
import logging
from typing import Optional

from apps.conversations.models import Conversation

logger = logging.getLogger(__name__)


class HandoffHandler:
    """
    Manages escalation from SalesAgent to human support.
    """

    @staticmethod
    def escalate(
        conversation: 'Conversation',
        session,
        organization,
        reason: str = 'User requested escalation',
    ) -> str:
        """
        Escalate conversation from AI to human.

        Args:
            conversation: Conversation instance
            session: SalesSession instance
            organization: Organization
            reason: Reason for escalation

        Returns:
            Handoff confirmation message
        """
        try:
            # Mark conversation as escalated (uses existing escalation mechanism)
            conversation.route_to = 'escalate_to_human'
            conversation.save(update_fields=['route_to'])

            # Update session state
            session.stage = 'handoff'
            session.save(update_fields=['stage'])

            logger.info(
                f'Escalated conversation {conversation.id} to human. '
                f'Reason: {reason}'
            )

            return HandoffHandler._handoff_message(reason)

        except Exception as e:
            logger.error(f'Handoff failed: {e}')
            return 'Un especialista se pondrá en contacto contigo pronto para ayudarte.'

    @staticmethod
    def _handoff_message(reason: str) -> str:
        """
        Generate handoff message for user.

        Args:
            reason: Reason for escalation

        Returns:
            User-facing handoff message
        """
        messages = {
            'user_requested': 'Conectándote con un especialista...',
            'complexity': 'Esta es una consulta compleja. Un especialista te ayudará de mejor manera.',
            'payment': 'Procesando tu compra... un especialista te guiará en los próximos pasos.',
            'custom_request': 'Entendemos tu solicitud. Un especialista se contactará contigo para detalles específicos.',
            'default': 'Pasando tu consulta a un especialista que podrá ayudarte mejor.',
        }

        return messages.get(reason, messages['default'])
