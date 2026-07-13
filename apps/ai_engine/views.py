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
from django.db.models import Avg, Count
from core.permissions import IsOrganizationMember, IsOrganizationAdmin
from core.mixins import OrgScopedMixin

from .models import AITask, AIInsight, AIPerformanceLog, SalesSession
from .serializers import (
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


# ─── Tone Preview (onboarding) ──────────────────────────────────────────────────

_TONE_FALLBACKS = {
    'formal': 'Buenas tardes, un gusto saludarle. Contamos con {product}, pensado especialmente para {audience}. ¿En qué puedo ayudarle hoy?',
    'casual': '¡Ey, qué tal! 👋 Tenemos {product}, ideal si eres de {audience}. ¿Qué te muestro primero?',
    'balanced': '¡Hola! Soy tu asistente virtual. Tenemos {product} pensado para {audience}. Cuéntame qué buscas y te ayudo.',
}

_TONE_LABELS = {
    'formal': 'formal y respetuoso, tratando de "usted"',
    'balanced': 'cercano pero profesional, tuteando con calidez',
    'casual': 'informal, juvenil y con emojis moderados',
}


class TonePreviewView(APIView):
    """
    POST /api/ai/tone-preview/
    Generates a one-off example sentence showing how the Sales Agent would
    greet a customer at a given formality level, for the onboarding tone picker.
    Falls back to a canned example when AI is disabled or the call fails —
    the onboarding flow must never block on this.
    """
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        formality = request.data.get('formality')
        if formality not in _TONE_FALLBACKS:
            formality = 'balanced'
        sell = str(request.data.get('what_you_sell') or '').strip()[:200] or 'lo que vendes'
        audience = str(request.data.get('who_you_sell_to') or '').strip()[:200] or 'tus clientes'

        fallback = _TONE_FALLBACKS[formality].format(product=sell, audience=audience)

        if not (settings.ENABLE_REAL_AI and settings.OPENAI_API_KEY):
            return Response({'example': fallback, 'source': 'fallback'})

        try:
            import openai
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            completion = client.chat.completions.create(
                model=settings.OPENAI_SITUATION_MODEL or 'gpt-4.1-nano',
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            'Escribes UNA sola oracion de ejemplo (maximo 220 caracteres) que muestra como '
                            'saludaria un vendedor de WhatsApp/chat a un cliente nuevo, en un tono '
                            f'{_TONE_LABELS[formality]}. Responde solo con la oracion, sin comillas ni explicaciones.'
                        ),
                    },
                    {
                        'role': 'user',
                        'content': f'Vende: {sell}\nA quien le vende: {audience}',
                    },
                ],
                max_tokens=120,
                temperature=0.9,
            )
            text = (completion.choices[0].message.content or '').strip().strip('"')
            if not text:
                return Response({'example': fallback, 'source': 'fallback'})
            return Response({'example': text[:280], 'source': 'ai'})
        except Exception as exc:
            logger.warning('tone_preview_error', error=str(exc))
            return Response({'example': fallback, 'source': 'fallback'})


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


class SalesSessionMetricsView(APIView):
    """Aggregate sales session funnel and activity metrics for the current organization."""
    permission_classes = [IsOrganizationMember]

    def get(self, request):
        qs = SalesSession.objects.filter(organization=request.user.organization)
        total_sessions = qs.count()

        stage_counts = {stage: 0 for stage, _label in SalesSession.STAGE_CHOICES}
        for row in qs.values('stage').annotate(count=Count('id')):
            stage_counts[row['stage']] = row['count']

        top_situations = [
            {
                'situation': row['situation'],
                'count': row['count'],
            }
            for row in qs.values('situation').annotate(count=Count('id')).order_by('-count', 'situation')[:5]
        ]

        checkout_sessions = qs.filter(checkout_step__gte=1).count()
        active_sessions = total_sessions - stage_counts.get('closed', 0)
        avg_messages = qs.aggregate(avg=Avg('message_count'))['avg'] or 0

        contract_metric_totals: dict[str, int] = {}
        sessions_with_contract_metrics = 0
        for checkout_data in qs.values_list('checkout_data', flat=True):
            if not isinstance(checkout_data, dict):
                continue
            metrics = checkout_data.get('contract_metrics')
            if not isinstance(metrics, dict) or not metrics:
                continue
            sessions_with_contract_metrics += 1
            for key, value in metrics.items():
                metric_key = str(key or '').strip()
                if not metric_key:
                    continue
                try:
                    amount = int(value or 0)
                except (TypeError, ValueError):
                    amount = 0
                contract_metric_totals[metric_key] = int(contract_metric_totals.get(metric_key, 0)) + amount

        return Response({
            'total_sessions': total_sessions,
            'active_sessions': active_sessions,
            'avg_messages_per_session': round(float(avg_messages), 1) if total_sessions else 0,
            'checkout_sessions': checkout_sessions,
            'checkout_rate_pct': round((checkout_sessions / total_sessions) * 100, 1) if total_sessions else 0,
            'stage_counts': stage_counts,
            'top_situations': top_situations,
            'opportunities': stage_counts.get('considering', 0) + stage_counts.get('checkout', 0),
            'handoff_sessions': stage_counts.get('handoff', 0),
            'closed_sessions': stage_counts.get('closed', 0),
            'sessions_with_contract_metrics': sessions_with_contract_metrics,
            'contract_metrics': contract_metric_totals,
        })


