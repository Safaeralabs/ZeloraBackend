from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils.dateparse import parse_datetime

from .schemas import Attachment, Channel, NormalizedEvent, utc_now


class InputProcessor:
    def normalize(self, raw_event: dict[str, Any]) -> NormalizedEvent:
        tenant_id = self._require_value(raw_event, 'tenant_id')
        channel = self._parse_channel(raw_event.get('channel'))
        text = self._extract_message_text(raw_event)

        return NormalizedEvent(
            tenant_id=tenant_id,
            channel=channel,
            contact_id=raw_event.get('contact_id'),
            conversation_id=raw_event.get('conversation_id'),
            sender_id=raw_event.get('sender_id'),
            message_text=text,
            attachments=self._extract_attachments(raw_event.get('attachments')),
            language=self._detect_language(raw_event, text),
            timestamp=self._parse_timestamp(raw_event.get('timestamp')),
            structured_payload=self._extract_structured_payload(raw_event),
            metadata=dict(raw_event.get('metadata') or {}),
            raw_event=dict(raw_event),
        )

    def _extract_message_text(self, raw_event: dict[str, Any]) -> str:
        for key in ('message_text', 'text', 'body'):
            value = raw_event.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        message = raw_event.get('message')
        if isinstance(message, dict):
            for key in ('text', 'body', 'caption'):
                value = message.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        structured_payload = raw_event.get('structured_payload')
        if isinstance(structured_payload, dict):
            for key in ('button_text', 'quick_reply_text', 'form_title', 'form_response'):
                value = structured_payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ''

    def _extract_structured_payload(self, raw_event: dict[str, Any]) -> dict[str, Any]:
        payload = raw_event.get('structured_payload')
        if isinstance(payload, dict):
            return dict(payload)

        message = raw_event.get('message')
        if isinstance(message, dict):
            structured_keys = {'buttons', 'quick_reply', 'form', 'interactive'}
            return {key: value for key, value in message.items() if key in structured_keys}

        return {}

    def _extract_attachments(self, raw_attachments: Any) -> list[Attachment]:
        if not isinstance(raw_attachments, list):
            return []

        attachments: list[Attachment] = []
        for item in raw_attachments:
            if not isinstance(item, dict):
                continue
            attachments.append(
                Attachment(
                    attachment_type=str(item.get('type', 'unknown')),
                    url=item.get('url'),
                    name=item.get('name'),
                    mime_type=item.get('mime_type'),
                    metadata=dict(item.get('metadata') or {}),
                )
            )
        return attachments

    def _detect_language(self, raw_event: dict[str, Any], text: str) -> str:
        explicit_language = raw_event.get('language')
        if isinstance(explicit_language, str) and explicit_language.strip():
            return explicit_language.strip().lower()

        sample = text.lower()
        spanish_markers = ('subsidio', 'certificado', 'cita', 'quiero', 'comprar')
        english_markers = ('subsidy', 'certificate', 'appointment', 'buy', 'units')

        if any(marker in sample for marker in spanish_markers):
            return 'es'
        if any(marker in sample for marker in english_markers):
            return 'en'
        return 'es'

    def _parse_timestamp(self, raw_timestamp: Any) -> datetime:
        if isinstance(raw_timestamp, datetime):
            return raw_timestamp
        if isinstance(raw_timestamp, str):
            parsed = parse_datetime(raw_timestamp)
            if parsed is not None:
                return parsed
        return utc_now()

    def _parse_channel(self, raw_channel: Any) -> Channel:
        if not isinstance(raw_channel, str):
            return Channel.UNKNOWN

        value = raw_channel.strip().lower()
        for channel in Channel:
            if value == channel.value:
                return channel
        return Channel.UNKNOWN

    def _require_value(self, raw_event: dict[str, Any], key: str) -> str:
        value = raw_event.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{key} is required')
        return value.strip()
