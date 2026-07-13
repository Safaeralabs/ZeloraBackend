"""
Handoff Handler — Manages escalation from sales agent to human.
"""
import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.conversations.models import Conversation
from apps.conversations.models import TimelineEvent

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
            previous_estado = str(conversation.estado or '')
            metadata = {**(conversation.metadata or {})}
            operator_state = {**(metadata.get('operator_state') or {})}
            operator_state['owner'] = 'humano'
            operator_state['commercial_status'] = 'escalado'
            operator_state['priority'] = 'alta'
            operator_state['follow_up'] = True
            operator_state['next_step'] = 'Atender conversacion escalada de inmediato.'
            operator_state['escalation_reason'] = reason
            operator_state['escalated_at'] = str(session.updated_at.isoformat() if getattr(session, 'updated_at', None) else '')
            metadata['operator_state'] = operator_state
            conversation.estado = 'escalado'
            conversation.metadata = metadata
            conversation.save(update_fields=['estado', 'metadata', 'updated_at'])

            # Update session state
            session.stage = 'handoff'
            session.save(update_fields=['stage'])
            TimelineEvent.objects.create(
                conversation=conversation,
                tipo='handoff',
                descripcion=f'Escalado automatico por Sales Agent. Razon: {reason}',
                metadata={'reason': reason, 'urgency': 'high'},
            )
            HandoffHandler._create_urgent_collab_note(conversation=conversation, organization=organization, reason=reason)
            HandoffHandler._broadcast_urgent_handoff(
                conversation=conversation,
                reason=reason,
                previous_estado=previous_estado,
            )

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
            
            'complexity': 'Esta es una consulta compleja. Un especialista te ayudara mejor.',
            
            'payment': 'Procesando tu compra... un especialista te guiara en los proximos pasos.',
            
            'shipping_delivery_unknown': 'Dejame validarlo un momento internamente; te conecto con un asesor para confirmarte el tiempo exacto de entrega.',
            'order_modification': 'Tu pedido ya fue confirmado. Un asesor va a revisar el cambio que pediste y te contacta.',
            'custom_request': 'Entendemos tu solicitud. Un especialista se contactará contigo para detalles específicos.',
            'default': 'Pasando tu consulta a un especialista que podrá ayudarte mejor.',
        }

        return messages.get(reason, messages['default'])

    @staticmethod
    def _create_urgent_collab_note(*, conversation: 'Conversation', organization, reason: str) -> None:
        try:
            from apps.workspace.models import CollabNote

            CollabNote.objects.create(
                organization=organization,
                conversation=conversation,
                author=None,
                note_type='warning',
                is_pinned=True,
                content=(
                    'ALERTA URGENTE: Conversacion escalada por IA. '
                    f'Razon: {reason}. Revisar y responder de inmediato.'
                ),
            )
        except Exception as exc:
            logger.warning('handoff_urgent_note_failed', conversation_id=str(conversation.id), error=str(exc))

    @staticmethod
    def _broadcast_urgent_handoff(*, conversation: 'Conversation', reason: str, previous_estado: str) -> None:
        try:
            channel_layer = get_channel_layer()
            if channel_layer is None:
                return

            org_group = f'org_{conversation.organization_id}'
            payload = {
                'id': str(conversation.id),
                'estado': conversation.estado,
                'updated_at': conversation.updated_at.isoformat() if conversation.updated_at else '',
                'metadata': conversation.metadata or {},
            }
            async_to_sync(channel_layer.group_send)(
                org_group,
                {
                    'type': 'conversation.updated',
                    'conversation_id': str(conversation.id),
                    'event': 'conversation_upserted',
                    'data': {'conversation': payload},
                }
            )
            async_to_sync(channel_layer.group_send)(
                org_group,
                {
                    'type': 'status.changed',
                    'conversation_id': str(conversation.id),
                    'estado': conversation.estado,
                    'previous_estado': previous_estado,
                }
            )
            async_to_sync(channel_layer.group_send)(
                org_group,
                {
                    'type': 'new.notification',
                    'message': 'Escalado urgente: se requiere atencion humana inmediata.',
                    'level': 'error',
                    'data': {
                        'kind': 'urgent_handoff',
                        'urgency': 'high',
                        'conversation_id': str(conversation.id),
                        'reason': reason,
                    },
                }
            )
        except Exception as exc:
            logger.warning('handoff_urgent_broadcast_failed', conversation_id=str(conversation.id), error=str(exc))



