"""
Follow-Up Engine — Proactive recovery of warm leads.

A real salesperson does not wait in silence: when a customer with buying
intent (considering/checkout) goes quiet, the agent sends one gentle,
brand-styled nudge. Runs from a periodic Celery task (see ai_engine.tasks).

Hard limits:
  - only sessions in 'considering' or 'checkout' with no confirmed order
  - respects sales_agent.followup_mode ('suave'/'activo', anything else = off)
  - never exceeds sales_agent.max_followups per conversation
  - minimum spacing between nudges, and never on conversations owned by a human
  - deterministic copy (no LLM cost), passed through the brand guard
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from .brand import BrandVoice
from .validator import ResponseValidator

logger = logging.getLogger(__name__)


class FollowUpEngine:
    # followup_mode → hours of inactivity before the first nudge
    MODE_DELAY_HOURS = {
        'suave': 4,
        'activo': 2,
    }
    MIN_SPACING_HOURS = 20   # between consecutive nudges in one conversation
    MAX_AGE_HOURS = 72       # older than this the lead is cold — leave it alone
    ELIGIBLE_STAGES = ('considering', 'checkout')
    ELIGIBLE_CHANNELS = ('app', 'web', 'whatsapp')
    ELIGIBLE_CONVERSATION_STATES = ('nuevo', 'en_proceso')

    # ── Sweep entry point ─────────────────────────────────────────────────────

    @classmethod
    def sweep(cls, now=None) -> dict:
        """Scan all orgs for stale high-intent sessions and nudge them."""
        from apps.ai_engine.models import SalesSession

        now = now or timezone.now()
        min_delay = min(cls.MODE_DELAY_HOURS.values())
        candidates = (
            SalesSession.objects
            .filter(
                stage__in=cls.ELIGIBLE_STAGES,
                updated_at__lte=now - timedelta(hours=min_delay),
                updated_at__gte=now - timedelta(hours=cls.MAX_AGE_HOURS),
            )
            .select_related('conversation', 'conversation__contact', 'organization')
        )

        sent = 0
        skipped = 0
        runtime_configs: dict = {}
        for session in candidates.iterator():
            org_id = str(session.organization_id)
            if org_id not in runtime_configs:
                runtime_configs[org_id] = BrandVoice.load_runtime_config(session.organization)
            try:
                if cls.process_session(session, runtime_configs[org_id], now=now):
                    sent += 1
                else:
                    skipped += 1
            except Exception as exc:
                skipped += 1
                logger.error('Follow-up failed for session %s: %s', session.id, exc)

        logger.info('Follow-up sweep done: %s sent, %s skipped', sent, skipped)
        return {'status': 'ok', 'sent': sent, 'skipped': skipped}

    @classmethod
    def process_session(cls, session, runtime_config: dict, now=None) -> bool:
        """Nudge one session if eligible. Returns True when a message was sent."""
        now = now or timezone.now()
        conversation = session.conversation
        eligible, reason = cls._is_eligible(session, conversation, runtime_config, now)
        if not eligible:
            logger.debug('Follow-up skipped for session %s: %s', session.id, reason)
            return False

        followup_state = dict((session.checkout_data or {}).get('followup_state') or {})
        followup_number = int(followup_state.get('count') or 0) + 1

        text = cls._build_message(
            session=session,
            organization=session.organization,
            runtime_config=runtime_config,
            followup_number=followup_number,
        )
        text = ResponseValidator.validate(
            text, {'brand_guard': BrandVoice.brand_guard(runtime_config)}
        )
        if not text:
            return False

        cls._deliver(conversation, text, followup_number=followup_number)

        checkout_data = dict(session.checkout_data or {})
        checkout_data['followup_state'] = {
            'count': followup_number,
            'last_at': now.isoformat(),
        }
        session.checkout_data = checkout_data
        session.save(update_fields=['checkout_data', 'updated_at'])
        return True

    # ── Eligibility ───────────────────────────────────────────────────────────

    @classmethod
    def _is_eligible(cls, session, conversation, runtime_config: dict, now) -> tuple[bool, str]:
        sales_agent = (runtime_config or {}).get('sales_agent') or {}

        if not sales_agent.get('enabled', True):
            return False, 'sales_agent_disabled'

        mode = str(sales_agent.get('followup_mode') or 'suave').strip().lower()
        delay_hours = cls.MODE_DELAY_HOURS.get(mode)
        if delay_hours is None:
            return False, f'followup_mode_off:{mode}'

        if session.stage not in cls.ELIGIBLE_STAGES:
            return False, f'stage:{session.stage}'
        if conversation.canal not in cls.ELIGIBLE_CHANNELS:
            return False, f'channel:{conversation.canal}'
        if conversation.estado not in cls.ELIGIBLE_CONVERSATION_STATES:
            return False, f'estado:{conversation.estado}'

        operator_state = ((conversation.metadata or {}).get('operator_state') or {})
        if operator_state.get('owner') == 'humano':
            return False, 'human_owned'

        checkout_data = dict(session.checkout_data or {})
        if str(checkout_data.get('order_id') or '').strip():
            return False, 'order_already_placed'

        max_followups = int(sales_agent.get('max_followups') or 3)
        followup_state = dict(checkout_data.get('followup_state') or {})
        if int(followup_state.get('count') or 0) >= max_followups:
            return False, 'max_followups_reached'

        last_followup_at = cls._parse_iso(followup_state.get('last_at'))
        if last_followup_at and now - last_followup_at < timedelta(hours=cls.MIN_SPACING_HOURS):
            return False, 'followup_spacing'

        last_activity = conversation.last_message_at or session.updated_at
        inactivity = now - last_activity
        if inactivity < timedelta(hours=delay_hours):
            return False, 'still_active'
        if inactivity > timedelta(hours=cls.MAX_AGE_HOURS):
            return False, 'lead_too_cold'

        last_message = conversation.messages.order_by('-timestamp').first()
        if last_message is None or last_message.role == 'user':
            # We owe the customer a reply — a nudge would be wrong here.
            return False, 'last_message_from_user'

        return True, 'ok'

    @staticmethod
    def _parse_iso(value):
        if not value:
            return None
        try:
            from datetime import datetime
            parsed = datetime.fromisoformat(str(value))
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed)
            return parsed
        except (ValueError, TypeError):
            return None

    # ── Message copy ──────────────────────────────────────────────────────────

    @classmethod
    def _build_message(cls, *, session, organization, runtime_config: dict, followup_number: int) -> str:
        sales_agent = (runtime_config or {}).get('sales_agent') or {}
        agent_name = str(sales_agent.get('name') or '').strip()
        product_title = cls._resolve_product_title(session, organization)

        if agent_name:
            greeting = f'Hola, soy {agent_name} de {organization.name}.'
        else:
            greeting = f'Hola, te escribo de {organization.name}.'

        product_ref = f' con {product_title}' if product_title else ''

        if followup_number >= 2:
            # Last gentle attempt: leave the door open, zero pressure.
            if session.stage == 'checkout':
                body = (
                    f'Tu pedido{product_ref} sigue guardado por si quieres retomarlo. '
                    'Si prefieres dejarlo para otro momento, no hay problema; aqui estare.'
                )
            else:
                body = (
                    f'Quedo atento por si aun te interesa{product_ref or " lo que vimos"}. '
                    'Si tienes alguna duda de precio, envio o disponibilidad, te la resuelvo aqui mismo.'
                )
        elif session.stage == 'checkout':
            body = (
                f'Dejamos tu pedido casi listo{product_ref}. '
                '¿Quieres que lo terminemos? Solo nos falta confirmar tus datos y queda creado.'
            )
        else:
            body = (
                f'Quede pendiente de ti{product_ref}. '
                '¿Te quedo alguna duda de precio, envio o disponibilidad? Te la resuelvo aqui mismo.'
            )

        return f'{greeting} {body}'

    @staticmethod
    def _resolve_product_title(session, organization) -> str:
        from .catalog import CatalogService

        candidate_ids = [str(item) for item in (session.selected_products or []) if str(item).strip()]
        candidate_ids += [str(item) for item in (session.shown_products or []) if str(item).strip()]
        for product_id in candidate_ids[:3]:
            product = CatalogService.get_product_by_id(product_id, organization)
            if product and str(product.get('title') or '').strip():
                return str(product['title']).strip()
        return ''

    # ── Delivery ──────────────────────────────────────────────────────────────

    @classmethod
    def _deliver(cls, conversation, text: str, *, followup_number: int):
        from apps.conversations.models import Message

        message = Message.objects.create(
            conversation=conversation,
            role='bot',
            content=text,
            metadata={'followup': {'number': followup_number, 'kind': 'sales_recovery'}},
        )
        conversation.last_message_at = message.timestamp
        conversation.save(update_fields=['last_message_at', 'updated_at'])

        cls._broadcast(conversation, message)

        if conversation.canal == 'whatsapp':
            phone = str(getattr(conversation.contact, 'telefono', '') or '').strip()
            if phone:
                try:
                    from tasks.channel_tasks import send_whatsapp_message
                    send_whatsapp_message.delay(
                        phone=phone,
                        message=text,
                        org_id=str(conversation.organization_id),
                        conv_id=str(conversation.id),
                    )
                except Exception as exc:
                    logger.error('Follow-up WhatsApp dispatch failed: %s', exc)

        logger.info(
            'Follow-up #%s sent for conversation %s (%s)',
            followup_number, conversation.id, conversation.canal,
        )
        return message

    @staticmethod
    def _broadcast(conversation, message):
        """Push to the public chat socket (app/web) and the admin inbox."""
        try:
            from apps.channels_config.views import (
                _broadcast_public_appchat_message,
                _broadcast_public_webchat_message,
            )
            _broadcast_public_appchat_message(conversation, message)
            _broadcast_public_webchat_message(conversation, message)
        except Exception as exc:
            logger.warning('Follow-up public broadcast failed: %s', exc)

        try:
            from tasks.ai_tasks import _broadcast_new_message
            _broadcast_new_message(conversation, message)
        except Exception as exc:
            logger.warning('Follow-up inbox broadcast failed: %s', exc)
