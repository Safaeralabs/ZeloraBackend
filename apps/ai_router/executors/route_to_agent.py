"""
RouteToAgentExecutor — routes to a specialized AI agent.

Sales:      uses the full SalesAgent (funnel stage, tools, structured output).
Marketing:  direct LLM reply with marketing-focused prompt.
Operations: direct LLM reply with operations-focused prompt.
"""
from __future__ import annotations
import structlog
from .base import BaseExecutor

logger = structlog.get_logger(__name__)

_DEFAULT_SYSTEM_PROMPTS = {
    'marketing': (
        'Eres un especialista en marketing digital para e-commerce en LatAm. '
        'Ayudas a identificar oportunidades de venta y comunicar mensajes clave de manera efectiva. '
        'Responde con recomendaciones concretas y orientadas a resultados. Máximo 3 oraciones.'
    ),
    'operations': (
        'Eres un especialista en operaciones de e-commerce. '
        'Ayudas con consultas sobre estado de pedidos, stock, fulfillment y logística. '
        'Responde con precisión. Si no tienes el dato exacto, pide el número de pedido. Máximo 3 oraciones.'
    ),
}

_HEURISTIC_REPLIES = {
    'general': 'Puedo ayudarte con informacion general de la marca, sus servicios y politicas basicas. ¿Que te gustaria saber?',
    'marketing': 'Tenemos novedades especiales disponibles. ¿Quieres que te cuente sobre nuestras promociones actuales?',
    'operations': 'Puedo revisar el estado de tu pedido. ¿Me puedes compartir tu número de orden o cédula?',
}


class RouteToAgentExecutor(BaseExecutor):
    def __init__(self, agent_type: str):
        self.agent_type = agent_type

    def execute(self, *, conversation, message, decision, organization) -> str | None:
        if self.agent_type == 'sales':
            return self._run_sales_agent(
                conversation=conversation,
                message=message,
                decision=decision,
                organization=organization,
            )
        return self._run_generic_agent(
            conversation=conversation,
            message=message,
            decision=decision,
            organization=organization,
        )

    # ── Sales Agent ────────────────────────────────────────────────────────────

    def _run_sales_agent(self, *, conversation, message, decision, organization) -> str | None:
        from apps.ai_engine.sales_agent import SalesAgent

        try:
            agent = SalesAgent()
            result = agent.run(
                message_text=message.content,
                conversation=conversation,
                organization=organization,
                router_decision=decision,
            )

            self._persist_sales_state(conversation, result)

            # Persist structured log (non-blocking)
            self._persist_sales_log(result, conversation, organization)

            # If handoff needed, also update conversation state
            if result.handoff.needed:
                from apps.conversations.models import TimelineEvent
                conversation.estado = 'escalado'
                conversation.save(update_fields=['estado', 'updated_at'])
                TimelineEvent.objects.create(
                    conversation=conversation,
                    tipo='escalated',
                    descripcion=f'Escalado por Sales Agent. Razón: {result.handoff.reason}',
                    metadata={
                        'agent': 'sales_agent',
                        'stage': result.stage,
                        'decision_id': decision.decision_id,
                    },
                )

            logger.info(
                'sales_agent_executed',
                org_id=str(organization.id),
                conv_id=str(conversation.id),
                stage=result.stage,
                decision=result.decision,
                handoff=result.handoff.needed,
                products_found=result.context_used.get('products_found', 0),
            )

            return result.reply_text or 'Con gusto te ayudo con tu consulta. ¿Qué producto estás buscando?'

        except Exception as exc:
            logger.error('sales_agent_error', error=str(exc), exc_info=True)
            return '¡Gracias por tu interés! ¿Qué producto estás buscando? Te ayudo a encontrar la mejor opción.'

    def _persist_sales_log(self, result, conversation, organization) -> None:
        try:
            from apps.ai_engine.models import SalesAgentLog

            metadata = (getattr(conversation, 'metadata', None) or {})
            evaluation = metadata.get('last_evaluation') if isinstance(metadata, dict) else {}
            evaluation_score = evaluation.get('score') if isinstance(evaluation, dict) else None
            evaluation_flags = evaluation.get('flags') if isinstance(evaluation, dict) else []
            evaluation_coherencia = evaluation.get('coherencia') if isinstance(evaluation, dict) else None
            evaluation_naturalidad = evaluation.get('naturalidad') if isinstance(evaluation, dict) else None
            evaluation_brand_fit = evaluation.get('brand_fit') if isinstance(evaluation, dict) else None
            evaluation_cta_quality = evaluation.get('cta_quality') if isinstance(evaluation, dict) else None
            if not isinstance(evaluation_flags, list):
                evaluation_flags = []

            SalesAgentLog.objects.create(
                organization=organization,
                conversation=conversation,
                stage=result.stage,
                confidence=result.confidence,
                decision=result.decision,
                handoff_needed=result.handoff.needed,
                handoff_reason=result.handoff.reason or '',
                products_shown=result.products_shown,
                recommended_actions=[a.to_dict() for a in result.recommended_actions],
                context_used=result.context_used,
                evaluation_score=evaluation_score,
                evaluation_coherencia=evaluation_coherencia,
                evaluation_naturalidad=evaluation_naturalidad,
                evaluation_brand_fit=evaluation_brand_fit,
                evaluation_cta_quality=evaluation_cta_quality,
                evaluation_flags=evaluation_flags,
                channel=getattr(conversation, 'canal', '') or '',
            )
        except Exception as exc:
            logger.warning('sales_agent_log_persist_failed', error=str(exc))

    def _persist_sales_state(self, conversation, result) -> None:
        try:
            metadata = {**(conversation.metadata or {})}
            metadata['sales_state'] = {
                'stage': result.stage,
                'close_signals': result.context_used.get('close_signals', []),
                'closing_ready': bool(result.context_used.get('closing_ready')),
                'decision': result.decision,
                'buyer_profile': result.buyer_profile.to_dict(),
            }

            operator_state = {**(metadata.get('operator_state') or {})}
            operator_state['active_ai_agent'] = 'sales'
            if result.handoff.needed:
                operator_state['commercial_status'] = 'escalado'
            else:
                operator_state['commercial_status'] = self._map_sales_stage_to_commercial_status(result.stage)
            operator_state['opportunity'] = result.stage in {'considering', 'intent_to_buy', 'checkout_blocked'}
            operator_state['follow_up'] = result.stage == 'follow_up_needed'
            operator_state['next_step'] = self._next_step_from_sales_result(result)
            metadata['operator_state'] = operator_state

            conversation.metadata = metadata
            conversation.save(update_fields=['metadata', 'updated_at'])
        except Exception as exc:
            logger.warning('sales_agent_state_persist_failed', error=str(exc))

    def _map_sales_stage_to_commercial_status(self, stage: str) -> str:
        if stage == 'discovering':
            return 'en_conversacion'
        if stage in {'considering', 'intent_to_buy'}:
            return 'interesado'
        if stage in {'checkout_blocked', 'follow_up_needed'}:
            return 'esperando_respuesta'
        if stage == 'lost':
            return 'perdido'
        return 'en_conversacion'

    def _next_step_from_sales_result(self, result) -> str:
        signals = result.context_used.get('close_signals', []) or []
        if result.handoff.needed:
            return 'Tomar conversacion y continuar cierre manual.'
        if 'payment_intent' in signals:
            return 'Presentar metodos de pago y cerrar pedido.'
        if 'explicit_buy_intent' in signals:
            return 'Confirmar producto y dejar pedido listo.'
        if result.stage == 'checkout_blocked':
            return 'Quitar friccion de pago o disponibilidad.'
        if result.stage == 'follow_up_needed':
            return 'Retomar con seguimiento breve y una sola pregunta util.'
        if result.stage == 'considering':
            return 'Reducir opciones y llevar a una decision.'
        return 'Calificar necesidad y llevar a recomendacion.'

    # ── Generic agents (marketing, operations) ─────────────────────────────────

    def _run_generic_agent(self, *, conversation, message, decision, organization) -> str | None:
        from apps.conversations.models import TimelineEvent
        from apps.knowledge_base.models import KBArticle
        from django.conf import settings
        from django.db.models import Q

        TimelineEvent.objects.create(
            conversation=conversation,
            tipo='handoff',
            descripcion=f'Derivado a agente IA: {self.agent_type}',
            metadata={'agent_type': self.agent_type, 'decision_id': decision.decision_id},
        )

        system_prompt = self._resolve_system_prompt(organization)

        user_message = message.content
        words = [w for w in user_message.lower().split() if len(w) > 3][:5]
        q_filter = Q()
        for w in words:
            q_filter |= Q(title__icontains=w) | Q(content__icontains=w)

        kb_articles = KBArticle.objects.filter(
            organization=organization, status='published',
        ).filter(q_filter)[:3]

        context = '\n'.join([f'### {a.title}\n{a.content[:400]}' for a in kb_articles])

        if getattr(settings, 'ENABLE_REAL_AI', False) and getattr(settings, 'OPENAI_API_KEY', ''):
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                full_prompt = system_prompt
                if context:
                    full_prompt += f'\n\nContexto:\n{context}'
                completion = client.chat.completions.create(
                    model=decision.model_name or getattr(settings, 'OPENAI_ROUTER_MODEL', 'gpt-4.1-nano'),
                    messages=[
                        {'role': 'system', 'content': full_prompt},
                        {'role': 'user', 'content': user_message},
                    ],
                    max_tokens=300,
                    temperature=0.7,
                )
                reply = completion.choices[0].message.content
                if reply:
                    return reply
            except Exception as exc:
                logger.warning('generic_agent_llm_failed', agent_type=self.agent_type, error=str(exc))

        return _HEURISTIC_REPLIES.get(self.agent_type, '¿En qué puedo ayudarte?')

    def _resolve_system_prompt(self, organization) -> str:
        try:
            from apps.ai_engine.models import AIAgent
            agent_obj = AIAgent.objects.filter(
                organization=organization,
                agent_type=self.agent_type,
                is_active=True,
            ).first()
            if agent_obj and agent_obj.system_prompt:
                return agent_obj.system_prompt
        except Exception:
            pass
        return _DEFAULT_SYSTEM_PROMPTS.get(self.agent_type, '')
