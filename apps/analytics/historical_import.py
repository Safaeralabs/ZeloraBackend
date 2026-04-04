from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from django.conf import settings


EMAIL_RE = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.IGNORECASE)
PHONE_RE = re.compile(r'(?<!\d)(?:\+?57)?[\s\-]?(?:3\d{2}|60\d|0?\d{7,10})(?:[\s\-]?\d{2,4}){1,3}(?!\d)')
DOC_RE = re.compile(r'(?i)\b(?:cc|cedula|cédula|ppt|nit|documento|doc)\s*[:.#-]?\s*[A-Z0-9-]{5,}\b')
IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')

TOPIC_RULES: dict[str, tuple[str, ...]] = {
    'subsidio_monetario': ('subsidio monet', 'subsidio', 'beneficiario'),
    'afiliaciones': ('afili', 'activar', 'conyuge', 'cónyuge', 'empresa debe afiliar'),
    'medio_de_pago': ('daviplata', 'cuenta', 'medio de pago', 'consignan', 'consignaban'),
    'certificados': ('certificado', 'certifica'),
    'vivienda': ('vivienda', 'beneficiario vivienda'),
    'educacion': ('tecnico laboral', 'técnico laboral', 'curso', 'formacion', 'formación'),
    'credito_social': ('credito', 'crédito'),
    'recreacion_turismo': ('restaurante', 'anas mai', 'recreacion', 'recreación', 'perla mar'),
}


@dataclass
class ImportedSession:
    conversation_id: str
    visitor_id: str
    topic: str
    route_hint: str
    stage: str
    resolved: bool
    needs_human: bool
    start_page_url: str
    start_page_title: str
    location: str
    source_host: str
    messages: list[dict[str, Any]]


def _fix_mojibake(value: str) -> str:
    if not isinstance(value, str):
        return value
    if 'Ã' not in value and 'Â' not in value:
        return value
    try:
        return value.encode('latin1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _sanitize_text(text: str) -> str:
    cleaned = _fix_mojibake(text or '')
    cleaned = EMAIL_RE.sub('[EMAIL]', cleaned)
    cleaned = DOC_RE.sub('[DOCUMENTO]', cleaned)
    cleaned = PHONE_RE.sub('[TELEFONO]', cleaned)
    cleaned = IP_RE.sub('[IP]', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _route_hint_from_topic(topic: str) -> str:
    sales_topics = {'catalogo', 'ventas', 'recreacion_turismo'}
    return 'sales' if topic in sales_topics else 'operations'


def _detect_topic(messages: list[str], start_page: str, page_title: str) -> str:
    haystack = ' '.join([start_page, page_title, *messages]).lower()
    for topic, patterns in TOPIC_RULES.items():
        if any(pattern in haystack for pattern in patterns):
            return topic
    return 'general'


def _normalize_stage(raw_stage: str, has_operator_reply: bool) -> str:
    if raw_stage == 'responded':
        return 'resolved' if has_operator_reply else 'pending'
    if raw_stage == 'engaged':
        return 'in_progress'
    if raw_stage == 'offline':
        return 'unanswered'
    return 'unknown'


def _iter_sessions(chats_path: Path):
    with chats_path.open('r', encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            visitor = row.get('visitor', {})
            chat_events = row.get('chat_events', {})
            for index, session in enumerate(chat_events.get('sessions', [])):
                yield visitor, session, index


def _build_session_record(visitor: dict[str, Any], session: dict[str, Any], index: int) -> ImportedSession | None:
    events = session.get('events', [])
    normalized_messages: list[dict[str, Any]] = []
    visitor_texts: list[str] = []
    has_operator_reply = False

    for event in events:
        event_type = event.get('type')
        params = event.get('params') or {}
        if event_type == 'visitor-message':
            text = _sanitize_text(params.get('text', ''))
            if not text:
                continue
            visitor_texts.append(text)
            normalized_messages.append({
                'role': 'user',
                'text': text,
                'timestamp': event.get('timestamp'),
            })
        elif event_type == 'operator-message':
            text = _sanitize_text(params.get('text', ''))
            if not text:
                continue
            has_operator_reply = True
            normalized_messages.append({
                'role': 'assistant',
                'text': text,
                'timestamp': event.get('timestamp'),
                'operator_id': params.get('operatorId'),
            })

    if not normalized_messages:
        return None

    start_page = session.get('startPage') or {}
    topic = _detect_topic(
        visitor_texts,
        _fix_mojibake(start_page.get('url', '') or ''),
        _fix_mojibake(start_page.get('title', '') or ''),
    )
    route_hint = _route_hint_from_topic(topic)
    stage = _normalize_stage(session.get('stage', ''), has_operator_reply)
    resolved = has_operator_reply and stage in {'resolved', 'in_progress'}
    needs_human = route_hint == 'operations' or not has_operator_reply
    conversation_id = f"{visitor.get('id', visitor.get('_id', 'visitor'))}:{index}:{session.get('startedAt', '')}"

    return ImportedSession(
        conversation_id=conversation_id,
        visitor_id=str(visitor.get('id') or visitor.get('_id') or ''),
        topic=topic,
        route_hint=route_hint,
        stage=stage,
        resolved=resolved,
        needs_human=needs_human,
        start_page_url=_fix_mojibake(start_page.get('url', '') or ''),
        start_page_title=_fix_mojibake(start_page.get('title', '') or ''),
        location=_fix_mojibake(visitor.get('location', '') or ''),
        source_host=_fix_mojibake(visitor.get('sourceHost', '') or ''),
        messages=normalized_messages,
    )


def _build_router_examples(sessions: list[ImportedSession]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for session in sessions:
        for message in session.messages:
            if message['role'] != 'user':
                continue
            examples.append({
                'conversation_id': session.conversation_id,
                'message_text': message['text'],
                'intent': session.topic,
                'route_hint': session.route_hint,
                'stage': session.stage,
                'needs_human': session.needs_human,
            })
    return examples


def _build_eval_examples(sessions: list[ImportedSession]) -> list[dict[str, Any]]:
    evals: list[dict[str, Any]] = []
    for session in sessions:
        messages = session.messages
        for idx, message in enumerate(messages[:-1]):
            if message['role'] != 'user':
                continue
            next_assistant = next((item for item in messages[idx + 1:] if item['role'] == 'assistant'), None)
            if not next_assistant:
                continue
            evals.append({
                'conversation_id': session.conversation_id,
                'topic': session.topic,
                'route_hint': session.route_hint,
                'user_message': message['text'],
                'ideal_response': next_assistant['text'],
            })
    return evals


def _build_kb_seed(sessions: list[ImportedSession]) -> list[dict[str, Any]]:
    grouped_questions: dict[str, list[str]] = defaultdict(list)
    grouped_answers: dict[str, list[str]] = defaultdict(list)
    for session in sessions:
        for message in session.messages:
            if message['role'] == 'user' and len(grouped_questions[session.topic]) < 25:
                grouped_questions[session.topic].append(message['text'])
            if message['role'] == 'assistant' and len(grouped_answers[session.topic]) < 25:
                grouped_answers[session.topic].append(message['text'])

    kb_items: list[dict[str, Any]] = []
    for topic, questions in grouped_questions.items():
        answers = grouped_answers.get(topic, [])
        kb_items.append({
            'topic': topic,
            'route_hint': _route_hint_from_topic(topic),
            'title': topic.replace('_', ' ').title(),
            'sample_questions': questions[:10],
            'sample_answers': answers[:10],
            'article_seed': (
                f"Tema detectado historicamente: {topic}. "
                f"Usa este bloque para crear un articulo o playbook especifico de la marca."
            ),
        })
    return kb_items


def _build_report(sessions: list[ImportedSession], router_examples: list[dict[str, Any]], evals: list[dict[str, Any]]) -> dict[str, Any]:
    topics = Counter(session.topic for session in sessions)
    routes = Counter(session.route_hint for session in sessions)
    stages = Counter(session.stage for session in sessions)
    return {
        'sessions': len(sessions),
        'router_examples': len(router_examples),
        'eval_examples': len(evals),
        'topics': topics.most_common(),
        'route_hints': routes.most_common(),
        'stages': stages.most_common(),
    }


def import_historical_chats(
    *,
    org_slug: str,
    chats_path: Path,
    output_dir: Path,
    source_name: str = 'web_chat_export',
) -> dict[str, Any]:
    sessions: list[ImportedSession] = []
    for visitor, session, index in _iter_sessions(chats_path):
        built = _build_session_record(visitor, session, index)
        if built is not None:
            sessions.append(built)

    router_examples = _build_router_examples(sessions)
    evals = _build_eval_examples(sessions)
    kb_seed = _build_kb_seed(sessions)
    report = _build_report(sessions, router_examples, evals)

    target_dir = output_dir / org_slug / source_name
    target_dir.mkdir(parents=True, exist_ok=True)

    normalized_path = target_dir / 'normalized_conversations.jsonl'
    with normalized_path.open('w', encoding='utf-8') as handle:
        for session in sessions:
            handle.write(json.dumps({
                'conversation_id': session.conversation_id,
                'visitor_id': session.visitor_id,
                'topic': session.topic,
                'route_hint': session.route_hint,
                'stage': session.stage,
                'resolved': session.resolved,
                'needs_human': session.needs_human,
                'start_page_url': session.start_page_url,
                'start_page_title': session.start_page_title,
                'location': session.location,
                'source_host': session.source_host,
                'messages': session.messages,
            }, ensure_ascii=False) + '\n')

    router_path = target_dir / 'router_examples.jsonl'
    with router_path.open('w', encoding='utf-8') as handle:
        for row in router_examples:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')

    evals_path = target_dir / 'eval_examples.jsonl'
    with evals_path.open('w', encoding='utf-8') as handle:
        for row in evals:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')

    kb_seed_path = target_dir / 'kb_seed.json'
    kb_seed_path.write_text(json.dumps(kb_seed, ensure_ascii=False, indent=2), encoding='utf-8')

    report_path = target_dir / 'report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    return {
        'target_dir': str(target_dir),
        'normalized_path': str(normalized_path),
        'router_path': str(router_path),
        'evals_path': str(evals_path),
        'kb_seed_path': str(kb_seed_path),
        'report_path': str(report_path),
        'report': report,
    }


def get_historical_imports_root() -> Path:
    return Path(settings.BASE_DIR) / 'data' / 'historical_imports'


def list_historical_imports(*, org_slug: str, output_dir: Path | None = None) -> list[dict[str, Any]]:
    root = output_dir or get_historical_imports_root()
    org_dir = root / org_slug
    if not org_dir.exists():
        return []

    imports: list[dict[str, Any]] = []
    for child in sorted(org_dir.iterdir(), key=lambda item: item.name, reverse=True):
        if not child.is_dir():
            continue
        report_path = child / 'report.json'
        kb_seed_path = child / 'kb_seed.json'
        if not report_path.exists():
            continue
        report = json.loads(report_path.read_text(encoding='utf-8'))
        imports.append({
            'source_name': child.name,
            'target_dir': str(child),
            'report': report,
            'has_kb_seed': kb_seed_path.exists(),
        })
    return imports
