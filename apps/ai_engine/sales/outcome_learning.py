"""
Outcome Learning — close the loop between conversations and results.

The strongest labels the system owns were unused until now:

  1. An Order created from chat marks the exchanges that led to it as
     WINNING — they become approved `winning_reply` LearningCandidates the
     ExampleBank retrieves as few-shot ("this is how this brand closes").
  2. A human rescuing an escalated conversation writes THE correct answer
     to the exact question the bot fumbled — the highest-signal training
     data there is. Those become approved `winning_reply` candidates too.
  3. Examples that were in the prompt when an order closed get their
     confidence rewarded; stale examples that never win decay, so the bank
     self-ranks by what actually sells.

Everything is deterministic (no LLM) and auto-approved on purpose: these are
the brand's own words with PII filtered out — the worst case is stylistic.
Hard FACTS (prices, policies) still go through the human-reviewed
LearningCandidate queue; nothing here writes to the KB.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from django.utils import timezone

from .voice_import import _contains_pii

logger = logging.getLogger(__name__)

#: Checkout-mechanics markers: exchanges about forms/payment data are not
#: persuasion and often carry PII — never learn from them.
_CHECKOUT_MARKERS = (
    'submit_compact_checkout', 'structured_payload', 'pedido #',
    'confirmo mi pedido', 'datos de envio',
)

WIN_CONFIDENCE = 0.80
HUMAN_CONFIDENCE = 0.85          # human corrections outrank bot wins
REWARD_STEP = 0.05
MAX_CONFIDENCE = 0.98
DECAY_FACTOR = 0.9
DECAY_AFTER_DAYS = 60
DECAY_FLOOR = 0.2


class OutcomeLearner:

    # ── 1. Wins from real orders ──────────────────────────────────────────────

    @classmethod
    def learn_from_order(cls, *, session, order_id: str) -> int:
        """
        Persist the persuasion exchanges (customer text → bot text) that
        preceded a confirmed order as approved winning_reply candidates.
        Returns how many candidates were created/reinforced.
        """
        conversation = session.conversation
        organization = session.organization
        exchanges = cls._winning_exchanges(conversation)
        saved = 0
        for exchange in exchanges:
            saved += cls._upsert_candidate(
                organization=organization,
                conversation=conversation,
                question=exchange['question'],
                answer=exchange['answer'],
                confidence=WIN_CONFIDENCE,
                metadata={
                    'origin': 'order_outcome',
                    'stage': str(session.stage or ''),
                    'situation': str(session.situation or ''),
                    'order_id': str(order_id),
                },
            )
        if saved:
            logger.info(
                'outcome_learning_order: %s winning exchanges saved for conv %s',
                saved, conversation.id,
            )
        return saved

    @classmethod
    def _winning_exchanges(cls, conversation, max_exchanges: int = 3) -> list[dict]:
        """Last clean customer→bot text pairs before the order, newest first
        skipped back past checkout mechanics."""
        messages = list(
            conversation.messages.order_by('timestamp').values('role', 'content', 'metadata')
        )
        exchanges: list[dict] = []
        for index in range(len(messages) - 1, 0, -1):
            if len(exchanges) >= max_exchanges:
                break
            message = messages[index]
            if message['role'] != 'bot':
                continue
            previous = messages[index - 1]
            if previous['role'] != 'user':
                continue
            question = str(previous['content'] or '').strip()
            answer = str(message['content'] or '').strip()
            if not cls._is_learnable_pair(question, answer, previous.get('metadata') or {}):
                continue
            exchanges.append({'question': question[:220], 'answer': answer[:400]})
        exchanges.reverse()
        return exchanges

    @classmethod
    def _is_learnable_pair(cls, question: str, answer: str, user_metadata: dict) -> bool:
        if len(question.split()) < 2 or len(answer) < 15:
            return False
        if (user_metadata or {}).get('structured_payload'):
            return False  # interactive/form turn, not conversation
        blob = f'{question} {answer}'.lower()
        if any(marker in blob for marker in _CHECKOUT_MARKERS):
            return False
        if _contains_pii(question) or _contains_pii(answer):
            return False
        return True

    # ── 2. Human corrections after escalation ─────────────────────────────────

    @classmethod
    def learn_from_human_rescue(cls, conversation, max_runs: int = 2) -> int:
        """
        Extract (customer question → human agent reply) pairs from an
        escalated conversation: what the human answered where the bot could
        not. Runs on resolve (same trigger as the LLM learning engine) and is
        a no-op for conversations without agent messages.
        """
        messages = list(
            conversation.messages.order_by('timestamp').values('role', 'content', 'metadata')
        )
        if not any(message['role'] == 'agent' for message in messages):
            return 0

        saved = 0
        runs_taken = 0
        index = 0
        while index < len(messages) and runs_taken < max_runs:
            if messages[index]['role'] != 'agent':
                index += 1
                continue
            # Collect the whole agent run (humans burst too).
            run_start = index
            reply_parts: list[str] = []
            while index < len(messages) and messages[index]['role'] == 'agent':
                text = str(messages[index]['content'] or '').strip()
                if text:
                    reply_parts.append(text)
                index += 1
            question = cls._last_user_question(messages, before=run_start)
            answer = '\n'.join(reply_parts[:4]).strip()
            if not question or not answer:
                continue
            if _contains_pii(question) or _contains_pii(answer) or len(answer) < 15:
                continue
            runs_taken += 1
            saved += cls._upsert_candidate(
                organization=conversation.organization,
                conversation=conversation,
                question=question[:220],
                answer=answer[:400],
                confidence=HUMAN_CONFIDENCE,
                metadata={'origin': 'human_correction'},
            )
        if saved:
            logger.info(
                'outcome_learning_rescue: %s human corrections saved for conv %s',
                saved, conversation.id,
            )
        return saved

    @staticmethod
    def _last_user_question(messages: list[dict], *, before: int) -> str:
        for index in range(before - 1, -1, -1):
            if messages[index]['role'] == 'user':
                question = str(messages[index]['content'] or '').strip()
                if len(question.split()) >= 2:
                    return question
                return ''
        return ''

    # ── 3. Reward / decay ─────────────────────────────────────────────────────

    @classmethod
    def reward_used_examples(cls, *, session) -> int:
        """
        Bump the confidence of the examples that were actually in the prompt
        during this (now converted) conversation. Ids are accumulated per
        turn in session.checkout_data['used_example_ids'] by the executor.
        """
        from apps.analytics.models import LearningCandidate

        ids = [
            str(item) for item in
            ((session.checkout_data or {}).get('used_example_ids') or [])
            if str(item).strip()
        ]
        if not ids:
            return 0
        rewarded = 0
        for candidate in LearningCandidate.objects.filter(
            id__in=ids, organization=session.organization,
        ):
            meta = dict(candidate.metadata or {})
            meta['wins'] = int(meta.get('wins') or 0) + 1
            meta['last_win_at'] = timezone.now().isoformat()
            candidate.metadata = meta
            candidate.confidence = min(MAX_CONFIDENCE, float(candidate.confidence or 0) + REWARD_STEP)
            candidate.save(update_fields=['metadata', 'confidence', 'updated_at'])
            rewarded += 1
        return rewarded

    @classmethod
    def decay_stale_examples(cls, organization=None) -> int:
        """
        Weekly hygiene: examples that never contributed to a sale lose
        confidence over time, so fresh winners naturally outrank them in the
        ExampleBank (which sorts by confidence). Floor keeps them retrievable
        for orgs with little data.
        """
        from apps.analytics.models import LearningCandidate
        from apps.ai_engine.sales.examples import EXAMPLE_KINDS

        cutoff = timezone.now() - timedelta(days=DECAY_AFTER_DAYS)
        queryset = LearningCandidate.objects.filter(
            kind__in=EXAMPLE_KINDS,
            status='approved',
            confidence__gt=DECAY_FLOOR,
            created_at__lt=cutoff,
        )
        if organization is not None:
            queryset = queryset.filter(organization=organization)

        decayed = 0
        for candidate in queryset.iterator():
            meta = candidate.metadata or {}
            if int(meta.get('wins') or 0) > 0:
                continue  # winners keep their rank
            candidate.confidence = max(DECAY_FLOOR, float(candidate.confidence or 0) * DECAY_FACTOR)
            candidate.save(update_fields=['confidence', 'updated_at'])
            decayed += 1
        if decayed:
            logger.info('outcome_learning_decay: %s stale examples decayed', decayed)
        return decayed

    # ── Shared upsert ─────────────────────────────────────────────────────────

    @staticmethod
    def _upsert_candidate(
        *, organization, conversation, question: str, answer: str,
        confidence: float, metadata: dict,
    ) -> int:
        from apps.analytics.models import LearningCandidate

        fingerprint = hashlib.sha256(f'{question}|{answer}'.encode('utf-8')).hexdigest()[:64]
        candidate, created = LearningCandidate.objects.get_or_create(
            organization=organization,
            kind='winning_reply',
            fingerprint=fingerprint,
            defaults={
                'conversation': conversation,
                'status': 'approved',
                'title': question[:255],
                'source_question': question,
                'proposed_answer': answer,
                'confidence': confidence,
                'metadata': {**metadata, 'wins': 1},
            },
        )
        if not created:
            # Same exchange won again: reinforce instead of duplicating.
            meta = dict(candidate.metadata or {})
            meta['wins'] = int(meta.get('wins') or 0) + 1
            candidate.metadata = meta
            candidate.evidence_count = int(candidate.evidence_count or 1) + 1
            candidate.confidence = min(MAX_CONFIDENCE, float(candidate.confidence or 0) + 0.03)
            candidate.save(update_fields=['metadata', 'evidence_count', 'confidence', 'updated_at'])
        return 1
