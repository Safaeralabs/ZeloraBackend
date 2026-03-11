"""
Campaign Celery tasks:
  - launch_campaign      — Resolve audience, split into batches, dispatch
  - send_campaign_batch  — Send campaign messages to a batch of contacts
  - finalize_campaign    — Chord callback: mark campaign complete + update counters
  - send_campaign        — Convenience alias
"""
import structlog
from celery import shared_task, chord
from django.utils import timezone

logger = structlog.get_logger(__name__)

BATCH_SIZE = 50  # Contacts per batch task


@shared_task(
    bind=True,
    name='tasks.campaign_tasks.launch_campaign',
    max_retries=1,
    queue='campaigns',
)
def launch_campaign(self, campaign_id: str) -> dict:
    """
    Launch a campaign:
      1. Validate campaign status
      2. Resolve audience contacts based on audience_filter JSON
      3. Split into batches of BATCH_SIZE
      4. Dispatch send_campaign_batch tasks via Celery chord
      5. Chord callback: finalize_campaign

    Returns the number of contacts targeted and batches dispatched.
    """
    try:
        from apps.campaigns.models import Campaign
        from apps.accounts.models import Contact

        campaign = Campaign.objects.select_related('organization', 'template').get(id=campaign_id)

        if campaign.status not in ('draft', 'scheduled'):
            logger.warning(
                'campaign_not_launchable',
                campaign_id=campaign_id,
                status=campaign.status,
            )
            return {'status': 'skipped', 'reason': f'status={campaign.status}'}

        # ── Mark as sending ───────────────────────────────────────────────────
        campaign.status = 'sending'
        campaign.save(update_fields=['status'])

        # ── Resolve audience ──────────────────────────────────────────────────
        audience_filter = campaign.target_filter or {}
        contacts_qs = Contact.objects.filter(
            organization=campaign.organization,
            is_active=True,
        )

        # Apply dynamic audience filters
        if audience_filter.get('tipo'):
            contacts_qs = contacts_qs.filter(tipo=audience_filter['tipo'])
        if audience_filter.get('tipo_afiliado'):
            contacts_qs = contacts_qs.filter(tipo_afiliado=audience_filter['tipo_afiliado'])
        if audience_filter.get('tag'):
            contacts_qs = contacts_qs.filter(tags__contains=[audience_filter['tag']])

        # Only include contacts with a phone number for WhatsApp campaigns
        if campaign.channel == 'whatsapp':
            contacts_qs = contacts_qs.exclude(telefono='')

        contact_ids = list(contacts_qs.values_list('id', flat=True).order_by('id'))

        if not contact_ids:
            campaign.status = 'sent'
            campaign.save(update_fields=['status'])
            logger.info('campaign_no_audience', campaign_id=campaign_id)
            return {'status': 'ok', 'total_contacts': 0, 'batches': 0}

        # ── Dispatch batches ──────────────────────────────────────────────────
        batches = [
            [str(cid) for cid in contact_ids[i:i + BATCH_SIZE]]
            for i in range(0, len(contact_ids), BATCH_SIZE)
        ]

        batch_tasks = [
            send_campaign_batch.s(str(campaign_id), batch)
            for batch in batches
        ]

        # Chord: run all batch tasks in parallel, then call finalize_campaign
        chord(batch_tasks)(finalize_campaign.s(str(campaign_id)))

        # Update total recipients
        campaign.total_recipients = len(contact_ids)
        campaign.save(update_fields=['total_recipients'])

        logger.info(
            'campaign_launched',
            campaign_id=campaign_id,
            total_contacts=len(contact_ids),
            batches=len(batches),
        )
        return {
            'status': 'ok',
            'total_contacts': len(contact_ids),
            'batches': len(batches),
        }

    except Exception as exc:
        logger.error('campaign_launch_error', campaign_id=campaign_id, error=str(exc), exc_info=True)
        # Revert status on failure
        try:
            from apps.campaigns.models import Campaign
            Campaign.objects.filter(id=campaign_id).update(status='draft')
        except Exception:
            pass
        raise self.retry(exc=exc)


# Convenience alias
send_campaign = launch_campaign


@shared_task(
    bind=True,
    name='tasks.campaign_tasks.send_campaign_batch',
    max_retries=3,
    default_retry_delay=15,
    queue='campaigns',
)
def send_campaign_batch(self, campaign_id: str, contact_ids: list) -> dict:
    """
    Send campaign messages to a batch of contacts.

    For each contact:
      - WhatsApp: dispatches send_whatsapp_message task
      - Email: dispatches send_email_message task (placeholder)
      - Telegram: placeholder

    Returns aggregated sent/failed counters for the batch.
    """
    from apps.campaigns.models import Campaign
    from apps.accounts.models import Contact
    from django.db.models import F

    campaign = Campaign.objects.select_related('organization').get(id=campaign_id)
    contacts = Contact.objects.filter(
        id__in=contact_ids,
        organization=campaign.organization,
        is_active=True,
    )

    sent = 0
    failed = 0

    # Get message template text
    message_text = ''
    if campaign.template and campaign.template.content:
        message_text = campaign.template.content
    else:
        message_text = f'Mensaje de la campaña: {campaign.name}'

    for contact in contacts:
        try:
            if campaign.channel == 'whatsapp' and contact.telefono:
                from tasks.channel_tasks import send_whatsapp_message
                # Personalise message with contact name
                personalised = message_text.replace('{{nombre}}', contact.nombre or '')
                send_whatsapp_message.delay(
                    phone=contact.telefono,
                    message=personalised,
                    org_id=str(campaign.organization_id),
                )
                sent += 1

            elif campaign.channel == 'email' and contact.email:
                # Placeholder: integrate SendGrid / SES here
                sent += 1

            else:
                logger.debug(
                    'campaign_contact_skipped',
                    contact_id=str(contact.id),
                    channel=campaign.channel,
                    has_phone=bool(contact.telefono),
                    has_email=bool(contact.email),
                )
                failed += 1

        except Exception as exc:
            logger.warning(
                'campaign_batch_item_failed',
                campaign_id=campaign_id,
                contact_id=str(contact.id),
                error=str(exc),
            )
            failed += 1

    # Atomically update counters
    Campaign.objects.filter(id=campaign_id).update(
        delivered=F('delivered') + sent,
        failed=F('failed') + failed,
    )

    logger.info(
        'campaign_batch_sent',
        campaign_id=campaign_id,
        batch_size=len(contact_ids),
        sent=sent,
        failed=failed,
    )
    return {'sent': sent, 'failed': failed}


@shared_task(name='tasks.campaign_tasks.finalize_campaign')
def finalize_campaign(results: list, campaign_id: str) -> dict:
    """
    Chord callback: aggregate batch results and mark campaign as sent.

    Args:
        results:     List of dicts returned by send_campaign_batch
        campaign_id: Campaign UUID
    """
    from apps.campaigns.models import Campaign

    total_sent = sum(r.get('sent', 0) for r in (results or []) if isinstance(r, dict))
    total_failed = sum(r.get('failed', 0) for r in (results or []) if isinstance(r, dict))

    Campaign.objects.filter(id=campaign_id).update(
        status='sent',
        sent_at=timezone.now(),
        delivered=total_sent,
        failed=total_failed,
    )

    logger.info(
        'campaign_finalized',
        campaign_id=campaign_id,
        sent=total_sent,
        failed=total_failed,
    )
    return {'status': 'sent', 'sent': total_sent, 'failed': total_failed}
