import structlog
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import Conversation, Message, TimelineEvent
from .serializers import ConversationListSerializer, ConversationDetailSerializer, MessageSerializer
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin

logger = structlog.get_logger(__name__)


class ConversationViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    filterset_fields = ['canal', 'estado', 'sentimiento']
    search_fields = ['contact__nombre', 'contact__apellido', 'intent']
    ordering_fields = ['updated_at', 'created_at']

    def get_queryset(self):
        return Conversation.objects.filter(
            organization=self.request.user.organization
        ).select_related('contact', 'assigned_agent').prefetch_related('messages')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ConversationDetailSerializer
        return ConversationListSerializer

    @action(detail=True, methods=['post'])
    def messages(self, request, pk=None):
        conv = self.get_object()
        serializer = MessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        msg = serializer.save(conversation=conv, role='agent')

        # Update conversation timestamp
        conv.updated_at = timezone.now()
        conv.save(update_fields=['updated_at'])

        # Async: send via channel if WhatsApp
        if conv.canal == 'whatsapp':
            try:
                from tasks.channel_tasks import send_whatsapp_message
                send_whatsapp_message.delay(str(conv.id), msg.content)
            except Exception:
                logger.warning('whatsapp_task_queue_failed', conversation_id=str(conv.id))

        # Broadcast via WebSocket
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'org_{conv.organization_id}',
                {
                    'type': 'conversation.updated',
                    'conversation_id': str(conv.id),
                    'event': 'new_message',
                }
            )
        except Exception:
            logger.warning('websocket_broadcast_failed', conversation_id=str(conv.id))

        logger.info('message_sent', conversation_id=str(conv.id), role='agent')
        return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def escalate(self, request, pk=None):
        conv = self.get_object()
        conv.estado = 'escalado'
        conv.save(update_fields=['estado', 'updated_at'])
        TimelineEvent.objects.create(
            conversation=conv,
            tipo='escalated',
            descripcion='Conversacion escalada por el asesor',
            actor=request.user,
        )
        logger.info('conversation_escalated', conversation_id=str(conv.id))
        return Response({'status': 'escalated'})

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        conv = self.get_object()
        conv.estado = 'resuelto'
        conv.resolved_at = timezone.now()
        conv.save(update_fields=['estado', 'resolved_at', 'updated_at'])
        TimelineEvent.objects.create(
            conversation=conv,
            tipo='resolved',
            descripcion='Conversacion resuelta',
            actor=request.user,
        )
        # Async: calculate QA score
        try:
            from tasks.ai_tasks import calculate_qa_score
            calculate_qa_score.delay(str(conv.id))
        except Exception:
            logger.warning('qa_score_task_queue_failed', conversation_id=str(conv.id))
        return Response({'status': 'resolved'})

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        from apps.accounts.models import User
        conv = self.get_object()
        agent_id = request.data.get('agent_id')
        try:
            agent = User.objects.get(id=agent_id, organization=request.user.organization)
            conv.assigned_agent = agent
            conv.estado = 'en_proceso'
            conv.save(update_fields=['assigned_agent', 'estado', 'updated_at'])
            TimelineEvent.objects.create(
                conversation=conv,
                tipo='agent_reply',
                descripcion=f'Asignado a {agent.full_name}',
                actor=request.user,
            )
            return Response({'status': 'assigned', 'agent': agent.full_name})
        except User.DoesNotExist:
            return Response({'error': 'Agent not found'}, status=status.HTTP_404_NOT_FOUND)
