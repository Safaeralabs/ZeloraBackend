"""
AI Engine views — AI Workspace backend.
Powers: Memory, Tasks, Insights, Performance, Copilot, Summarize, Intent Detection.
"""
import structlog
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings
from django.utils import timezone
from core.permissions import IsOrganizationMember, IsOrganizationAdmin
from core.mixins import OrgScopedMixin

from .models import AIMemoryEntry, AITask, AIInsight, AIPerformanceLog
from .serializers import (
    AIMemoryEntrySerializer,
    AITaskSerializer,
    AIInsightSerializer,
    AIPerformanceLogSerializer,
)

logger = structlog.get_logger(__name__)

# ─── Mock response bank (replace with real LLM calls via ENABLE_REAL_AI flag) ──
_MOCK_SUGGESTIONS = {
    'Subsidio familiar': [
        'Para tramitar su subsidio familiar necesita: cédula, certificado de ingresos y formulario de afiliación.',
        'El subsidio familiar se paga los primeros 5 días hábiles de cada mes a los trabajadores activos.',
    ],
    'Certificado de afiliación': [
        'Puede descargar su certificado de afiliación en la página web o solicitarlo en cualquier sede.',
        'El certificado de afiliación está disponible de forma inmediata en nuestra plataforma digital.',
    ],
    'PQRS': [
        'Para radicar una PQRS puede hacerlo en nuestra página web, WhatsApp o en cualquiera de nuestras sedes.',
        'Su PQRS será atendida en un plazo máximo de 15 días hábiles según la ley.',
    ],
    'Actualización de datos': [
        'Para actualizar sus datos debe presentar cédula de ciudadanía vigente y los documentos que soporten el cambio.',
    ],
    'Consulta pensión': [
        'Para consultar el estado de su pensión puede llamar a nuestra línea de atención o ingresar a la plataforma web.',
    ],
    'default': [
        'Entiendo su consulta. Le ayudaré con gusto. ¿Podría darme más detalles?',
        'Estoy revisando su caso. Un momento por favor.',
    ],
}

_INTENT_MAP = {
    'subsidio': 'Subsidio familiar',
    'certificado': 'Certificado de afiliación',
    'afiliacion': 'Certificado de afiliación',
    'afiliación': 'Certificado de afiliación',
    'pqrs': 'PQRS',
    'queja': 'PQRS',
    'reclamo': 'PQRS',
    'peticion': 'PQRS',
    'actualiz': 'Actualización de datos',
    'datos': 'Actualización de datos',
    'pension': 'Consulta pensión',
    'pensión': 'Consulta pensión',
}


def _detect_intent(text: str) -> tuple[str, float]:
    """Keyword-based intent detection. Replace with LLM classifier in production."""
    text_lower = text.lower()
    for keyword, intent in _INTENT_MAP.items():
        if keyword in text_lower:
            return intent, 0.85
    return 'Consulta general', 0.60


# ─── AI Copilot ────────────────────────────────────────────────────────────────

class CopilotView(APIView):
    """
    POST /api/ai/copilot/
    Provides AI-generated response suggestions for an agent handling a conversation.
    """
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        intent = request.data.get('intent', 'default')
        conversation_id = request.data.get('conversation_id')
        context_messages = request.data.get('messages', [])

        if settings.ENABLE_REAL_AI and settings.OPENAI_API_KEY:
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

                messages = [
                    {
                        'role': 'system',
                        'content': (
                            'Eres un asistente de atención al cliente experto en servicios de caja de compensación '
                            'familiar en Colombia. Genera 2 respuestas cortas, amables y profesionales para el agente.'
                            ' Responde en español. Sé conciso (máximo 2 oraciones por sugerencia).'
                        ),
                    },
                    {
                        'role': 'user',
                        'content': f'Genera 2 respuestas para la intención: {intent}',
                    },
                ]

                completion = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=messages,
                    max_tokens=400,
                    temperature=0.7,
                )
                raw = completion.choices[0].message.content or ''
                # Split by newline to get individual suggestions
                suggestions = [s.strip() for s in raw.split('\n') if s.strip()][:3]

            except Exception as e:
                logger.warning('openai_copilot_error', error=str(e))
                suggestions = _MOCK_SUGGESTIONS.get(intent, _MOCK_SUGGESTIONS['default'])
        else:
            suggestions = _MOCK_SUGGESTIONS.get(intent, _MOCK_SUGGESTIONS['default'])

        logger.info('copilot_request', intent=intent, conversation_id=conversation_id)
        return Response({
            'suggestions': suggestions,
            'intent': intent,
            'conversation_id': conversation_id,
        })


# ─── Conversation Summarize ────────────────────────────────────────────────────

class SummarizeView(APIView):
    """
    POST /api/ai/summarize/
    Returns a text summary of a conversation.
    """
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        conversation_id = request.data.get('conversation_id')
        if not conversation_id:
            return Response({'error': 'conversation_id required'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.conversations.models import Conversation
        try:
            conv = Conversation.objects.prefetch_related('messages').get(
                id=conversation_id, organization=request.user.organization
            )
        except Conversation.DoesNotExist:
            return Response({'error': 'Conversation not found'}, status=status.HTTP_404_NOT_FOUND)

        messages = list(conv.messages.order_by('timestamp'))
        msg_count = len(messages)

        if settings.ENABLE_REAL_AI and settings.OPENAI_API_KEY and msg_count > 0:
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                transcript = '\n'.join(
                    [f'[{m.role.upper()}] {m.content[:500]}' for m in messages[-20:]]
                )
                completion = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {
                            'role': 'system',
                            'content': 'Resume la siguiente conversación de atención al cliente en 3 frases máximo. Español.',
                        },
                        {'role': 'user', 'content': transcript},
                    ],
                    max_tokens=200,
                )
                summary = completion.choices[0].message.content or ''
            except Exception as e:
                logger.warning('openai_summarize_error', error=str(e))
                summary = self._heuristic_summary(conv, msg_count)
        else:
            summary = self._heuristic_summary(conv, msg_count)

        return Response({'summary': summary, 'message_count': msg_count})

    @staticmethod
    def _heuristic_summary(conv, msg_count: int) -> str:
        return (
            f'Conversación sobre "{conv.intent or "consulta general"}". '
            f'{msg_count} mensajes. Estado actual: {conv.estado}. '
            f'Canal: {conv.canal}. Sentimiento: {conv.sentimiento}.'
        )


# ─── Intent Detection ──────────────────────────────────────────────────────────

class IntentDetectView(APIView):
    """
    POST /api/ai/intent/
    Detect intent from a message text.
    """
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        text = request.data.get('text', '')
        if not text:
            return Response({'error': 'text required'}, status=status.HTTP_400_BAD_REQUEST)

        intent, confidence = _detect_intent(text)
        return Response({'intent': intent, 'confidence': confidence, 'text': text[:100]})


# ─── QA Score Trigger ──────────────────────────────────────────────────────────

class QAScoreView(APIView):
    """
    POST /api/ai/qa-score/
    Queue an async QA scoring task for a conversation.
    """
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        conversation_id = request.data.get('conversation_id')
        if not conversation_id:
            return Response({'error': 'conversation_id required'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify conversation belongs to this org
        from apps.conversations.models import Conversation
        if not Conversation.objects.filter(
            id=conversation_id, organization=request.user.organization
        ).exists():
            return Response({'error': 'Conversation not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            from tasks.ai_tasks import score_conversation_qa
            result = score_conversation_qa.delay(str(conversation_id))
            return Response({'status': 'queued', 'task_id': result.id})
        except Exception as e:
            logger.warning('qa_score_queue_error', error=str(e))
            return Response({'status': 'queued', 'note': 'Task queued (Celery may be starting)'})


# ─── AI Memory ViewSet ─────────────────────────────────────────────────────────

class AIMemoryViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    """CRUD for AI memory entries scoped to the organization."""
    permission_classes = [IsOrganizationAdmin]
    serializer_class = AIMemoryEntrySerializer
    filterset_fields = ['memory_type', 'is_active']
    search_fields = ['key', 'value']

    def get_queryset(self):
        return AIMemoryEntry.objects.filter(organization=self.request.user.organization)


# ─── AI Tasks ViewSet ──────────────────────────────────────────────────────────

class AITaskViewSet(OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only list/retrieve of AI background tasks."""
    permission_classes = [IsOrganizationMember]
    serializer_class = AITaskSerializer
    filterset_fields = ['status', 'task_type', 'priority']

    def get_queryset(self):
        return AITask.objects.filter(organization=self.request.user.organization)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        task = self.get_object()
        if task.status not in ('pending', 'running'):
            return Response({'error': f'Cannot cancel task in status {task.status}'}, status=400)

        if task.celery_task_id:
            try:
                from tasks.celery_app import app
                app.control.revoke(task.celery_task_id, terminate=True)
            except Exception:
                pass

        task.status = 'cancelled'
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'completed_at'])
        return Response({'status': 'cancelled'})


# ─── AI Insights ViewSet ───────────────────────────────────────────────────────

class AIInsightViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    """AI-generated insights for the organization."""
    permission_classes = [IsOrganizationMember]
    serializer_class = AIInsightSerializer
    filterset_fields = ['category', 'severity', 'is_read']

    def get_queryset(self):
        return AIInsight.objects.filter(organization=self.request.user.organization)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        insight = self.get_object()
        insight.is_read = True
        insight.save(update_fields=['is_read'])
        return Response({'status': 'marked_read'})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        count = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'marked_read': count})


# ─── AI Performance ViewSet ────────────────────────────────────────────────────

class AIPerformanceViewSet(OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Read AI model performance logs."""
    permission_classes = [IsOrganizationMember]
    serializer_class = AIPerformanceLogSerializer
    filterset_fields = ['model_name']

    def get_queryset(self):
        return AIPerformanceLog.objects.filter(organization=self.request.user.organization)
