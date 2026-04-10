import structlog
import json
from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import Conversation, Message, TimelineEvent
from .serializers import ConversationListSerializer, ConversationDetailSerializer, MessageSerializer
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin
from apps.accounts.models import Contact

logger = structlog.get_logger(__name__)

DEFAULT_OPERATOR_STATE = {
    'owner': 'ia',
    'active_ai_agent': '',
    'commercial_status': 'nuevo',
    'priority': 'media',
    'follow_up': False,
    'opportunity': False,
    'next_step': '',
    'conversation_summary': '',
    'escalation_reason': '',
}


def _clear_active_flow(conversation):
    metadata = {**(conversation.metadata or {})}
    if 'active_flow' not in metadata:
        return
    metadata.pop('active_flow', None)
    conversation.metadata = metadata
    conversation.save(update_fields=['metadata', 'updated_at'])


def _merged_operator_state(conversation):
    metadata = conversation.metadata or {}
    return {**DEFAULT_OPERATOR_STATE, **(metadata.get('operator_state') or {})}


def _update_operator_state(conversation, patch: dict):
    metadata = {**(conversation.metadata or {})}
    operator_state = _merged_operator_state(conversation)
    operator_state.update({key: value for key, value in patch.items() if value is not None})
    metadata['operator_state'] = operator_state
    if operator_state.get('commercial_status') in {'cerrado', 'venta_lograda', 'perdido'}:
        metadata.pop('active_flow', None)
    conversation.metadata = metadata
    conversation.save(update_fields=['metadata', 'updated_at'])
    return operator_state


def _normalize_contact_channel(channel: str) -> str:
    return channel if channel in {'whatsapp', 'instagram', 'web', 'tiktok', 'email', 'telegram'} else 'web'


def _mark_conversation_read(conversation):
    metadata = {**(conversation.metadata or {})}
    inbox_state = {**(metadata.get('inbox_state') or {})}
    inbox_state['last_read_at'] = timezone.now().isoformat()
    metadata['inbox_state'] = inbox_state
    conversation.metadata = metadata
    conversation.save(update_fields=['metadata', 'updated_at'])
    return inbox_state


def _broadcast_public_appchat_message(conversation, message):
    if conversation.canal != 'app' or not conversation.external_id:
        return
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        from .consumers import build_public_appchat_group

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            build_public_appchat_group(conversation.organization.slug, conversation.external_id),
            {
                'type': 'appchat.message',
                'conversation_id': str(conversation.id),
                'session_id': conversation.external_id,
                'message': MessageSerializer(message).data,
            },
        )
    except Exception:
        logger.warning('public_appchat_broadcast_failed', conversation_id=str(conversation.id), message_id=str(message.id))


class ConversationViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    filterset_fields = ['canal', 'estado', 'sentimiento']
    search_fields = ['contact__nombre', 'contact__apellido', 'intent']
    ordering_fields = ['updated_at', 'created_at']

    def get_queryset(self):
        return Conversation.objects.filter(
            organization=self.request.user.organization
        ).select_related('contact', 'assigned_agent').prefetch_related('messages', 'timeline', 'collab_notes')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ConversationDetailSerializer
        return ConversationListSerializer

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Return conversation counts: total and current calendar month."""
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        qs = self.get_queryset()
        return Response({
            'this_month': qs.filter(created_at__gte=start_of_month).count(),
            'total': qs.count(),
        })

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        conversation = self.get_object()
        _mark_conversation_read(conversation)
        response.data['unread'] = False
        return response

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
                if conv.contact and conv.contact.telefono:
                    task_kwargs = {
                        'phone': conv.contact.telefono,
                        'message': msg.content,
                        'org_id': str(conv.organization_id),
                        'conv_id': str(conv.id),
                    }
                    if getattr(settings, 'ENABLE_REAL_WHATSAPP', False):
                        send_whatsapp_message.delay(**task_kwargs)
                    else:
                        send_whatsapp_message(**task_kwargs)
                else:
                    logger.warning('whatsapp_missing_contact_phone', conversation_id=str(conv.id))
            except Exception:
                logger.warning('whatsapp_task_queue_failed', conversation_id=str(conv.id))

        # Broadcast via WebSocket
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            conversation_payload = ConversationListSerializer(conv).data
            async_to_sync(channel_layer.group_send)(
                f'org_{conv.organization_id}',
                {
                    'type': 'conversation.updated',
                    'conversation_id': str(conv.id),
                    'event': 'conversation_upserted',
                    'data': {'conversation': conversation_payload},
                }
            )
            async_to_sync(channel_layer.group_send)(
                f'org_{conv.organization_id}',
                {
                    'type': 'conversation.message',
                    'conversation_id': str(conv.id),
                    'message': MessageSerializer(msg).data,
                    'conversation': conversation_payload,
                }
            )
        except Exception:
            logger.warning('websocket_broadcast_failed', conversation_id=str(conv.id))

        _broadcast_public_appchat_message(conv, msg)
        logger.info('message_sent', conversation_id=str(conv.id), role='agent')
        return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def escalate(self, request, pk=None):
        conv = self.get_object()
        reason = (request.data.get('reason') or '').strip()
        conv.estado = 'escalado'
        conv.save(update_fields=['estado', 'updated_at'])
        operator_state = _update_operator_state(conv, {
            'owner': 'humano',
            'commercial_status': 'escalado',
            'priority': 'alta',
            'follow_up': True,
            'escalation_reason': reason or _merged_operator_state(conv).get('escalation_reason', ''),
        })
        TimelineEvent.objects.create(
            conversation=conv,
            tipo='escalated',
            descripcion='Conversacion escalada por el asesor',
            actor=request.user,
            metadata={'reason': operator_state.get('escalation_reason', '')},
        )
        logger.info('conversation_escalated', conversation_id=str(conv.id))
        # Async: extract learnings before handing off to human (use Celery for reliability).
        try:
            from apps.ai_engine.tasks import extract_conversation_learnings
            extract_conversation_learnings.delay(str(conv.id))
        except Exception:
            logger.warning('learning_engine_task_queue_failed', conversation_id=str(conv.id))
        return Response({'status': 'escalated'})

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        conv = self.get_object()
        conv.estado = 'resuelto'
        conv.resolved_at = timezone.now()
        conv.save(update_fields=['estado', 'resolved_at', 'updated_at'])
        _clear_active_flow(conv)
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
        # Async: extract conversation learnings for the AI Learning Engine (use Celery for reliability).
        try:
            from apps.ai_engine.tasks import extract_conversation_learnings
            extract_conversation_learnings.delay(str(conv.id))
        except Exception:
            logger.warning('learning_engine_task_queue_failed', conversation_id=str(conv.id))
        return Response({'status': 'resolved'})

    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        conv = self.get_object()
        conv.estado = 'abierto'
        conv.resolved_at = None
        conv.save(update_fields=['estado', 'resolved_at', 'updated_at'])
        _update_operator_state(conv, {'commercial_status': 'en_proceso', 'owner': 'ia'})
        TimelineEvent.objects.create(
            conversation=conv,
            tipo='reopened',
            descripcion='Conversacion reabierta por operador',
            actor=request.user,
        )
        return Response({'status': 'reopened'})

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
            _update_operator_state(conv, {'owner': 'humano'})
            TimelineEvent.objects.create(
                conversation=conv,
                tipo='agent_reply',
                descripcion=f'Asignado a {agent.full_name}',
                actor=request.user,
            )
            return Response({'status': 'assigned', 'agent': agent.full_name})
        except User.DoesNotExist:
            return Response({'error': 'Agent not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'], url_path='take-over')
    def take_over(self, request, pk=None):
        conv = self.get_object()
        conv.assigned_agent = request.user
        conv.estado = 'en_proceso'
        conv.save(update_fields=['assigned_agent', 'estado', 'updated_at'])
        _update_operator_state(conv, {'owner': 'humano'})
        TimelineEvent.objects.create(
            conversation=conv,
            tipo='handoff',
            descripcion=f'Conversacion tomada por {request.user.full_name}',
            actor=request.user,
        )
        return Response({'status': 'taken_over', 'agent': request.user.full_name})

    @action(detail=True, methods=['post'], url_path='return-to-ai')
    def return_to_ai(self, request, pk=None):
        conv = self.get_object()
        _update_operator_state(conv, {'owner': 'ia'})
        TimelineEvent.objects.create(
            conversation=conv,
            tipo='handoff',
            descripcion='Conversacion devuelta a IA',
            actor=request.user,
        )
        return Response({'status': 'returned_to_ai'})

    @action(detail=True, methods=['patch'], url_path='operator-state')
    def operator_state(self, request, pk=None):
        conv = self.get_object()
        allowed = {
            'owner',
            'commercial_status',
            'priority',
            'follow_up',
            'opportunity',
            'next_step',
            'conversation_summary',
            'escalation_reason',
        }
        patch = {key: request.data.get(key) for key in allowed if key in request.data}
        if not patch:
            raise ValidationError('No operator state fields provided')
        state = _update_operator_state(conv, patch)
        if 'owner' in patch and patch['owner'] == 'humano' and conv.assigned_agent_id is None:
            conv.assigned_agent = request.user
            conv.estado = 'en_proceso'
            conv.save(update_fields=['assigned_agent', 'estado', 'updated_at'])
        TimelineEvent.objects.create(
            conversation=conv,
            tipo='note',
            descripcion='Estado operativo actualizado',
            actor=request.user,
            metadata={'operator_state': state},
        )
        return Response({'status': 'updated', 'operator_state': state})

    @action(detail=True, methods=['post'], url_path='notes')
    def add_note(self, request, pk=None):
        conv = self.get_object()
        content = (request.data.get('content') or '').strip()
        note_type = (request.data.get('note_type') or 'note').strip()
        if not content:
            raise ValidationError('content is required')
        from apps.workspace.models import CollabNote
        note = CollabNote.objects.create(
            organization=request.user.organization,
            conversation=conv,
            author=request.user,
            note_type=note_type,
            content=content,
        )
        TimelineEvent.objects.create(
            conversation=conv,
            tipo='note',
            descripcion=f'Nota interna agregada ({note_type})',
            actor=request.user,
            metadata={'note_id': str(note.id), 'note_type': note_type},
        )
        return Response({
            'id': str(note.id),
            'content': note.content,
            'note_type': note.note_type,
            'author_nombre': request.user.full_name,
            'created_at': note.created_at.isoformat(),
            'is_pinned': note.is_pinned,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path='contact')
    def update_contact(self, request, pk=None):
        conv = self.get_object()
        nombre = (request.data.get('nombre') or '').strip()
        telefono = (request.data.get('telefono') or '').strip()
        email = (request.data.get('email') or '').strip().lower()

        if not any([nombre, telefono, email]):
            raise ValidationError('Debes enviar al menos un dato de contacto')

        contact = conv.contact
        if contact is None:
            lookup = Q()
            if email:
                lookup |= Q(email__iexact=email)
            if telefono:
                lookup |= Q(telefono=telefono)
            if lookup:
                contact = (
                    Contact.objects.filter(organization=request.user.organization)
                    .filter(lookup)
                    .order_by('-updated_at')
                    .first()
                )
            if contact is None:
                if not nombre:
                    raise ValidationError({'nombre': 'El nombre es obligatorio para crear el contacto'})
                contact = Contact.objects.create(
                    organization=request.user.organization,
                    nombre=nombre,
                    email=email,
                    telefono=telefono,
                    tipo='cliente',
                    canal=_normalize_contact_channel(conv.canal),
                )

        changed_fields = []
        if nombre and contact.nombre != nombre:
            contact.nombre = nombre
            changed_fields.append('nombre')
        if 'telefono' in request.data and contact.telefono != telefono:
            contact.telefono = telefono
            changed_fields.append('telefono')
        if 'email' in request.data and contact.email != email:
            contact.email = email
            changed_fields.append('email')
        normalized_channel = _normalize_contact_channel(conv.canal)
        if contact.canal != normalized_channel:
            contact.canal = normalized_channel
            changed_fields.append('canal')
        if changed_fields:
            contact.save(update_fields=[*changed_fields, 'updated_at'])

        if conv.contact_id != contact.id:
            conv.contact = contact
            conv.updated_at = timezone.now()
            conv.save(update_fields=['contact', 'updated_at'])

        TimelineEvent.objects.create(
            conversation=conv,
            tipo='note',
            descripcion='Datos del cliente actualizados manualmente',
            actor=request.user,
            metadata={
                'contact_id': str(contact.id),
                'nombre': contact.nombre,
                'telefono': contact.telefono,
                'email': contact.email,
            },
        )

        return Response({
            'status': 'updated',
            'contact_id': str(contact.id),
            'nombre': contact.nombre,
            'telefono': contact.telefono,
            'email': contact.email,
        })

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        conv = self.get_object()
        state = _mark_conversation_read(conv)
        return Response({'status': 'read', 'inbox_state': state})

    @action(detail=True, methods=['get'], url_path='export-json')
    def export_json(self, request, pk=None):
        conv = self.get_object()
        payload = ConversationDetailSerializer(conv).data
        payload['exported_at'] = timezone.now().isoformat()
        payload['exported_by'] = {
            'id': str(request.user.id),
            'name': request.user.full_name,
            'email': request.user.email,
        }
        response = HttpResponse(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            content_type='application/json; charset=utf-8',
        )
        response['Content-Disposition'] = f'attachment; filename="conversation-{conv.id}.json"'
        return response

    @action(detail=False, methods=['post'], url_path='export-json-batch')
    def export_json_batch(self, request):
        raw_ids = request.data.get('conversation_ids') or []
        if not isinstance(raw_ids, list) or not raw_ids:
            raise ValidationError({'conversation_ids': 'Debes enviar una lista de conversaciones.'})

        conversations = list(
            self.get_queryset()
            .filter(id__in=raw_ids)
            .order_by('-updated_at')[:500]
        )
        payload = {
            'exported_at': timezone.now().isoformat(),
            'exported_by': {
                'id': str(request.user.id),
                'name': request.user.full_name,
                'email': request.user.email,
            },
            'count': len(conversations),
            'conversations': ConversationDetailSerializer(conversations, many=True).data,
        }
        response = HttpResponse(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            content_type='application/json; charset=utf-8',
        )
        response['Content-Disposition'] = 'attachment; filename="conversations-export.json"'
        return response
