"""
Contact Memory Service — soft, cross-conversation customer signals.

Complements CustomerHistoryService (hard Order facts): this holds inferred
continuity signals that otherwise vanish once a conversation closes —
budget range, category interests, last detected intent/objection, whether
they've converted. Kept in sync from the SAME per-turn hook that already
persists SalesSession state (SessionManager.update()), so there's no extra
LLM call and no separate summarization job: just one cheap upsert on a
single row per contact.

Anonymous contacts (no email/phone yet) are skipped entirely — there is no
stable identity to attach continuity to until checkout resolves one.
"""
from __future__ import annotations


class ContactMemoryService:
    @staticmethod
    def sync_from_session(*, session, situation: str, context: dict) -> None:
        """Upsert this contact's ContactMemory from the current turn's state."""
        contact = getattr(session.conversation, 'contact', None)
        if contact is None or not (contact.email or contact.telefono):
            return

        try:
            from django.utils import timezone
            from apps.ai_engine.models import ContactMemory

            memory, _created = ContactMemory.objects.get_or_create(
                organization=session.organization, contact=contact,
            )

            # First turn of a (possibly brand new) conversation for a contact
            # we may already know from a previous one.
            if session.message_count == 1:
                memory.conversation_count = (memory.conversation_count or 0) + 1

            if session.budget_min is not None:
                memory.inferred_budget_min = session.budget_min
            if session.budget_max is not None:
                memory.inferred_budget_max = session.budget_max

            if session.category_interest:
                prefs = list(memory.category_preferences or [])
                if session.category_interest not in prefs:
                    prefs.append(session.category_interest)
                memory.category_preferences = prefs[-8:]

            if session.objections:
                memory.last_objection = session.objections[-1]

            if situation and situation != 'discovery':
                memory.last_intent = situation

            if context.get('recommended_products'):
                shown = [p['id'] for p in context['recommended_products'] if p.get('id')]
                if shown:
                    memory.last_products_shown = list(dict.fromkeys(shown))[-5:]
                    memory.total_products_viewed = (memory.total_products_viewed or 0) + len(shown)

            if context.get('order_completed'):
                memory.converted = True

            memory.last_conversation_at = timezone.now()
            memory.save()
        except Exception:
            pass  # Continuity memory is an enhancement, never blocks the reply.

    @staticmethod
    def fetch_summary(*, contact) -> str:
        """
        Compact prompt-ready summary, or '' for first-time/anonymous
        contacts. Only surfaced when conversation_count > 1 — a "returning
        customer" note is noise on someone's very first conversation.
        """
        if contact is None:
            return ''

        from apps.ai_engine.models import ContactMemory

        memory = ContactMemory.objects.filter(contact=contact).first()
        if not memory or memory.conversation_count <= 1:
            return ''

        lines = [
            '## Cliente recurrente',
            f'Este contacto ya tuvo {memory.conversation_count} conversaciones antes.',
        ]
        if memory.inferred_budget_min or memory.inferred_budget_max:
            lines.append(
                f'Presupuesto estimado: ${memory.inferred_budget_min or "?"}-${memory.inferred_budget_max or "?"}'
            )
        if memory.category_preferences:
            lines.append(f'Categorias de interes previas: {", ".join(memory.category_preferences[-5:])}')
        if memory.last_objection:
            lines.append(f'Ultima objecion detectada: {memory.last_objection}')
        if memory.converted:
            lines.append('Ya ha comprado antes.')
        lines.append('')
        return '\n'.join(lines)
