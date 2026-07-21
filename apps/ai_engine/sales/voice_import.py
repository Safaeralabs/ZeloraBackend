"""
Voice Import — compile a brand's REAL chat style into a voice_card.

The onboarding form captures adjectives ("cercano y energico"); real chats
capture how the brand actually types: message length, burst rhythm, emoji
palette, price shorthand, punctuation quirks. LLMs imitate evidence far
better than descriptions, so this module turns an inbox export into:

  - a `voice_card` dict (see settings_schema._VOICE_CARD_DEFAULTS)
  - `voice_examples` (short, PII-free real brand messages for few-shot)
  - example exchanges (customer → brand reply) for the ExampleBank

Everything here is deterministic (no LLM) and brand-agnostic: it works for
any store's export. Entry points:

  parse_instagram_inbox(path, brand_name=None) -> list[dict]      (Meta export dir)
  parse_chat_payload(files, pasted_text, brand_name) -> dict      (self-serve upload)
  compile_voice_card(conversations) -> dict
  select_example_exchanges(conversations) -> list[dict]
  seed_example_candidates(organization, exchanges) -> int

Sources supported by parse_chat_payload (auto-detected per file):
  - Meta/Instagram/Messenger HTML export (`message_1.html`)
  - WhatsApp .txt export (iOS `[fecha] Nombre: texto` and Android
    `fecha - Nombre: texto`, Spanish locales)
  - pasted plain text (`Nombre: texto` per line) as a universal fallback

Used by the `import_brand_voice` management command and the self-serve
voice-import endpoints (onboarding + knowledge base). Raw chat content is
parsed in memory and never persisted.
"""
from __future__ import annotations

import logging
import re
import statistics
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Instagram/Meta DM export parsing
# ──────────────────────────────────────────────────────────────────────────────

class _MetaExportHTMLParser(HTMLParser):
    """
    Parses one `message_1.html` from a Meta (Instagram/Facebook) DM export.
    Messages are divs with classes `_a6-h` (sender), `_a6-p` (content) and
    `_a6-o` (timestamp), newest first.
    """

    def __init__(self):
        super().__init__()
        self.messages: list[dict] = []
        self._stack: list[str] = []
        self._current: dict | None = None
        self._mode: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get('class', '') or ''
        self._stack.append(cls)
        if '_a6-h' in cls:
            self._current = {'sender': '', 'text': ''}
            self._mode = 'sender'
            self._buffer = []
        elif '_a6-p' in cls and self._current is not None:
            self._mode = 'text'
            self._buffer = []
        elif '_a6-o' in cls and self._current is not None:
            self._mode = 'when'
            self._buffer = []

    def handle_endtag(self, tag):
        cls = self._stack.pop() if self._stack else ''
        if self._current is None or self._mode is None:
            return
        joined = ' '.join(part for part in self._buffer if part).strip()
        if '_a6-h' in cls and self._mode == 'sender':
            self._current['sender'] = joined
            self._mode = None
        elif '_a6-p' in cls and self._mode == 'text':
            self._current['text'] = joined
            self._mode = None
        elif '_a6-o' in cls and self._mode == 'when':
            # Timestamp closes the message block.
            self.messages.append(self._current)
            self._current = None
            self._mode = None

    def handle_data(self, data):
        if self._current is not None and self._mode:
            self._buffer.append(data.strip())


def parse_meta_html(raw: str, name: str) -> dict | None:
    """Parse one Meta export HTML document into {'name', 'messages'} (no
    is_brand yet — resolved once all conversations are collected)."""
    # Meta exports write UTF-8 bytes escaped as latin-1 text.
    try:
        raw = raw.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    parser = _MetaExportHTMLParser()
    try:
        parser.feed(raw)
    except Exception as exc:
        logger.warning('Fallo el parseo HTML de %s: %s', name, exc)
        return None
    messages = list(reversed(parser.messages))  # export is newest-first
    if not messages:
        return None
    return {'name': name, 'messages': messages}


def parse_instagram_inbox(path: str, brand_name: str | None = None) -> list[dict]:
    """
    Parse a Meta DM export directory (one subfolder per conversation, each
    with `message_1.html`) into normalized conversations:

        [{'name': <folder>, 'messages': [{'sender', 'text', 'is_brand'}, ...]}]

    Messages come out in chronological order. `is_brand` is resolved against
    `brand_name` when given; otherwise the participant present in the most
    conversations is assumed to be the brand (it is in all of them).
    """
    root = Path(path)
    if not root.is_dir():
        raise ValueError(f'No es un directorio: {path}')

    conversations: list[dict] = []
    for html_file in sorted(root.glob('*/message_1.html')):
        try:
            raw = html_file.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning('No se pudo leer %s: %s', html_file, exc)
            continue
        parsed = parse_meta_html(raw, html_file.parent.name)
        if parsed:
            conversations.append(parsed)

    if not conversations:
        return []

    _mark_brand_messages(conversations, brand_name)
    return conversations


def _mark_brand_messages(conversations: list[dict], brand_name: str | None) -> str:
    brand = _resolve_brand_sender(conversations, brand_name)
    for conversation in conversations:
        for message in conversation['messages']:
            message['is_brand'] = message['sender'] == brand
    return brand


# ──────────────────────────────────────────────────────────────────────────────
# WhatsApp .txt export parsing (iOS + Android, Spanish locales)
# ──────────────────────────────────────────────────────────────────────────────

#: `14/07/26, 2:15 p. m.` / `14/07/2026 14:15:44` — date and time, both styles.
_WA_TIMESTAMP = r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s?[ap]\.?\s?m\.?)?'
_WA_IOS_LINE = re.compile(rf'^\[({_WA_TIMESTAMP})\]\s?(.*)$', re.IGNORECASE)
_WA_ANDROID_LINE = re.compile(rf'^({_WA_TIMESTAMP})\s+[-–]\s+(.*)$', re.IGNORECASE)

#: Direction marks WhatsApp sprinkles around media/system lines.
_WA_INVISIBLES = ('‎', '‏', '﻿')

#: WhatsApp system/media placeholders (no style value, some leak phone data).
_WA_SYSTEM_MARKERS = (
    'cifrado de extremo a extremo', 'cifrados de extremo a extremo',
    'multimedia omitido', 'imagen omitida', 'video omitido', 'audio omitido',
    'sticker omitido', 'gif omitido', 'documento omitido',
    'se eliminó este mensaje', 'se elimino este mensaje',
    'eliminaste este mensaje', 'se editó este mensaje', 'se edito este mensaje',
    'llamada perdida', 'videollamada perdida', '<adjunto:', '<attached:',
    'ubicación:', 'ubicacion:', 'location:', 'tarjeta de contacto omitida',
)


def _clean_wa_line(line: str) -> str:
    for mark in _WA_INVISIBLES:
        line = line.replace(mark, '')
    return line.rstrip('\n\r')


def _is_wa_system_text(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _WA_SYSTEM_MARKERS)


def parse_whatsapp_txt(raw: str, name: str) -> dict | None:
    """
    Parse one WhatsApp chat export (.txt) into {'name', 'messages'}.
    Handles both iOS (`[fecha] Nombre: texto`) and Android
    (`fecha - Nombre: texto`) formats and multi-line messages
    (continuation lines belong to the previous message).
    """
    messages: list[dict] = []
    current: dict | None = None

    for raw_line in raw.splitlines():
        line = _clean_wa_line(raw_line)
        if not line.strip():
            continue
        match = _WA_IOS_LINE.match(line) or _WA_ANDROID_LINE.match(line)
        if not match:
            # Continuation of the previous message (multi-line text).
            if current is not None:
                current['text'] = f"{current['text']}\n{line.strip()}".strip()
            continue
        body = match.group(2).strip()
        sender, sep, text = body.partition(': ')
        if not sep or not sender.strip() or len(sender) > 60:
            # System line ("Los mensajes están cifrados...", group events).
            current = None
            continue
        text = text.strip()
        if _is_wa_system_text(text):
            current = None
            continue
        current = {'sender': sender.strip(), 'text': text}
        messages.append(current)

    messages = [message for message in messages if message['text'].strip()]
    if len(messages) < 2:
        return None
    return {'name': name, 'messages': messages}


# ──────────────────────────────────────────────────────────────────────────────
# Pasted-text fallback + source auto-detection
# ──────────────────────────────────────────────────────────────────────────────

_PASTED_LINE = re.compile(r'^([^\s:][^:]{0,48}):\s+(.+)$')


def parse_pasted_text(raw: str, name: str = 'pegado') -> dict | None:
    """
    Universal fallback: `Nombre: texto` per line (covers TikTok, Telegram,
    email transcripts, anything the user can copy). WhatsApp-formatted pastes
    are recognized as such first.
    """
    as_whatsapp = parse_whatsapp_txt(raw, name)
    if as_whatsapp and len(as_whatsapp['messages']) >= 3:
        return as_whatsapp

    messages: list[dict] = []
    current: dict | None = None
    for raw_line in raw.splitlines():
        line = _clean_wa_line(raw_line).strip()
        if not line:
            current = None
            continue
        match = _PASTED_LINE.match(line)
        if match:
            sender = match.group(1).strip()
            text = match.group(2).strip()
            if _is_wa_system_text(text):
                current = None
                continue
            current = {'sender': sender, 'text': text}
            messages.append(current)
        elif current is not None:
            current['text'] = f"{current['text']}\n{line}".strip()

    senders = {message['sender'] for message in messages}
    if len(messages) < 4 or len(senders) < 2:
        return None
    return {'name': name, 'messages': messages}


def detect_source(filename: str, content: str) -> str:
    """'meta_html' | 'whatsapp_txt' | 'pasted' — best guess per file."""
    lowered_name = (filename or '').lower()
    head = content[:6000]
    if lowered_name.endswith(('.html', '.htm')) or '_a6-p' in head or '<html' in head.lower():
        return 'meta_html'
    sample_lines = [line for line in content.splitlines()[:60] if line.strip()]
    wa_hits = sum(
        1 for line in sample_lines
        if _WA_IOS_LINE.match(_clean_wa_line(line)) or _WA_ANDROID_LINE.match(_clean_wa_line(line))
    )
    if wa_hits >= 3:
        return 'whatsapp_txt'
    return 'pasted'


def parse_chat_payload(
    files: list[tuple[str, str]],
    pasted_text: str = '',
    brand_name: str | None = None,
) -> dict:
    """
    Parse a self-serve upload (list of (filename, text_content) pairs plus
    optional pasted text) into normalized conversations. Auto-detects the
    source per file. Returns:

        {
          'conversations': [...],                # with is_brand resolved
          'brand': '<detected brand sender>',
          'participants': [{'name', 'messages'}],  # for the "which one is you?" UI
          'sources': {'meta_html': n, 'whatsapp_txt': n, 'pasted': n},
          'skipped': ['file.ext', ...],
        }

    Everything happens in memory; nothing is written anywhere.
    """
    conversations: list[dict] = []
    sources: Counter = Counter()
    skipped: list[str] = []

    for filename, content in files:
        if not (content or '').strip():
            skipped.append(filename)
            continue
        source = detect_source(filename, content)
        if source == 'meta_html':
            parsed = parse_meta_html(content, filename)
        elif source == 'whatsapp_txt':
            parsed = parse_whatsapp_txt(content, filename)
        else:
            parsed = parse_pasted_text(content, filename)
        if parsed:
            conversations.append(parsed)
            sources[source] += 1
        else:
            skipped.append(filename)

    if (pasted_text or '').strip():
        parsed = parse_pasted_text(pasted_text, 'texto pegado')
        if parsed:
            conversations.append(parsed)
            sources['pasted'] += 1
        else:
            skipped.append('texto pegado')

    brand = _mark_brand_messages(conversations, brand_name) if conversations else ''

    participant_counts: Counter = Counter()
    for conversation in conversations:
        for message in conversation['messages']:
            if message.get('sender'):
                participant_counts[message['sender']] += 1
    participants = [
        {'name': sender, 'messages': count}
        for sender, count in participant_counts.most_common(12)
    ]

    return {
        'conversations': conversations,
        'brand': brand,
        'participants': participants,
        'sources': dict(sources),
        'skipped': skipped,
    }


def _resolve_brand_sender(conversations: list[dict], brand_name: str | None) -> str:
    senders_per_conversation = [
        {message['sender'] for message in conversation['messages'] if message['sender']}
        for conversation in conversations
    ]
    if brand_name:
        wanted = brand_name.strip().lower()
        for senders in senders_per_conversation:
            for sender in senders:
                if sender.strip().lower() == wanted:
                    return sender
    # The brand is present in (almost) every conversation; ties — e.g. one
    # single export file holding several customers — break by message volume,
    # because the seller writes far more than any one customer.
    presence = Counter()
    volume = Counter()
    for conversation, senders in zip(conversations, senders_per_conversation):
        for sender in senders:
            presence[sender] += 1
        for message in conversation['messages']:
            if message.get('sender'):
                volume[message['sender']] += 1
    if not presence:
        return ''
    return max(presence, key=lambda sender: (presence[sender], volume[sender]))


# ──────────────────────────────────────────────────────────────────────────────
# Noise / PII filters
# ──────────────────────────────────────────────────────────────────────────────

_NOISE_MARKERS = (
    'http://', 'https://', 'sent an attachment', 'click for audio',
    'liked a message', 'reacted ', 'you sent an attachment',
    # WhatsApp placeholders (also filtered at parse time; kept here as a
    # second net for pasted text)
    'multimedia omitido', 'imagen omitida', 'video omitido', 'audio omitido',
    'sticker omitido', 'documento omitido', 'se eliminó este mensaje',
    'se elimino este mensaje', 'cifrado de extremo a extremo',
)

_PII_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r'\b\d{7,}\b',                                    # phones / account numbers
        r'[\w.+-]+@[\w-]+\.[\w.]+',                       # emails
        # Latin-American street addresses (calle 16 # 16 E 40, cra 20 #12-83...)
        r'\b(calle|carrera|cra|carr|kra|krr|diagonal|transversal|avenida|av|mz|manzana)\.?\s*\d',
        r'\b(apto|apartamento|casa|torre|edificio|conjunto|porteria)\b.{0,30}\d',
        r'\b(nequi|bancolombia|daviplata|davivienda|bbva)\b',
    )
]


def _is_noise(text: str) -> bool:
    """Media placeholders, shares, reactions, audio — useless for style."""
    if not text or not text.strip():
        return True
    lowered = text.lower()
    return any(marker in lowered for marker in _NOISE_MARKERS)


def _contains_pii(text: str) -> bool:
    return any(pattern.search(text) for pattern in _PII_PATTERNS)


def _brand_text_messages(conversations: list[dict]) -> list[str]:
    return [
        message['text'].strip()
        for conversation in conversations
        for message in conversation['messages']
        if message.get('is_brand') and not _is_noise(message.get('text') or '')
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Voice card compilation (pure stats, no LLM)
# ──────────────────────────────────────────────────────────────────────────────

# Emoji plus optional skin-tone/variation modifier kept as one unit.
_EMOJI_RE = re.compile(
    '[\U0001F300-\U0001FAFF☀-➿⬀-⯿]'
    '[\U0001F3FB-\U0001F3FF️]?'
)

_GREETING_TOKENS = ('hola', 'holaa', 'holaaa', 'holi', 'buenas', 'buenos', 'hey', 'hello', 'hi')

_PRICE_SHORTHAND_RE = re.compile(r'\b\d{1,3}\s?mil\b', re.IGNORECASE)
_PRICE_FORMAL_RE = re.compile(r'\$\s?[\d.,]+')


def compile_voice_card(conversations: list[dict], *, min_messages: int = 10) -> dict:
    """
    Measure the brand's writing fingerprint from parsed conversations.

    Returns {'voice_card': {...}, 'voice_examples': [...], 'stats': {...}}.
    Empty/near-empty inputs produce an empty voice_card (never raises).

    `min_messages` guards against compiling a card from too little evidence.
    Organic chats need the default 10; a structured onboarding interview
    (every answer is on-topic selling) is reliable from ~6.
    """
    texts = _brand_text_messages(conversations)
    if len(texts) < max(1, min_messages):
        logger.warning('Muy pocos mensajes de marca (%s) para compilar voz', len(texts))
        return {'voice_card': {}, 'voice_examples': [], 'stats': {'brand_messages': len(texts)}}

    word_counts = [len(text.split()) for text in texts]
    median_words = int(statistics.median(word_counts))

    burst_runs = _brand_burst_runs(conversations)
    multi_ratio = (
        sum(1 for run in burst_runs if run >= 2) / len(burst_runs) if burst_runs else 0.0
    )
    rhythm = 'bursts' if multi_ratio >= 0.35 else 'single'
    max_burst = 3
    if burst_runs:
        max_burst = max(2, min(4, round(statistics.mean(run for run in burst_runs if run >= 1))))

    emoji_counts: Counter = Counter()
    messages_with_emoji = 0
    for text in texts:
        found = _EMOJI_RE.findall(text)
        if found:
            messages_with_emoji += 1
        emoji_counts.update(found)
    emoji_ratio = messages_with_emoji / len(texts)
    palette = [emoji for emoji, count in emoji_counts.most_common(4) if count >= 2]
    if emoji_ratio == 0:
        frequency = 'none'
    elif emoji_ratio < 0.25:
        frequency = 'low'
    elif emoji_ratio < 0.6:
        frequency = 'medium'
    else:
        frequency = 'high'

    price_style = _detect_price_style(texts)
    punctuation_style = _detect_punctuation_style(texts)
    signature_phrases = _detect_signature_phrases(texts)
    greeting_style = _detect_greeting_style(conversations)

    formatting_rules: list[str] = []
    if rhythm == 'bursts':
        formatting_rules.append('Nunca uses listas, numeraciones ni parrafos largos: escribe como mensajes de chat.')

    voice_card = {
        'message_rhythm': rhythm,
        'max_burst_messages': max_burst,
        'typical_message_words': median_words,
        'price_style': price_style,
        'emoji_palette': palette,
        'emoji_frequency': frequency,
        'punctuation_style': punctuation_style,
        'signature_phrases': signature_phrases,
        'greeting_style': greeting_style,
        'formatting_rules': formatting_rules,
        'source': 'imported',
    }
    return {
        'voice_card': voice_card,
        'voice_examples': _select_voice_examples(texts),
        'stats': {
            'brand_messages': len(texts),
            'median_words': median_words,
            'multi_message_turn_ratio': round(multi_ratio, 2),
            'emoji_message_ratio': round(emoji_ratio, 2),
        },
    }


def _brand_burst_runs(conversations: list[dict]) -> list[int]:
    """Lengths of consecutive brand-message runs (media counts for rhythm)."""
    runs: list[int] = []
    for conversation in conversations:
        current = 0
        for message in conversation['messages']:
            if message.get('is_brand'):
                current += 1
            elif current:
                runs.append(current)
                current = 0
        if current:
            runs.append(current)
    return runs


def _detect_price_style(texts: list[str]) -> str:
    shorthand = sum(1 for text in texts if _PRICE_SHORTHAND_RE.search(text))
    formal = sum(1 for text in texts if _PRICE_FORMAL_RE.search(text))
    # Small structured corpora (onboarding interview) mention price once or
    # twice; demanding 3 absolute hits there would blank a clear signal.
    needed = 3 if len(texts) >= 30 else 2
    if shorthand >= needed and shorthand > formal * 2:
        example = next(
            (_PRICE_SHORTHAND_RE.search(text).group(0) for text in texts if _PRICE_SHORTHAND_RE.search(text)),
            '35mil',
        )
        return f'como "{example}" (nunca "$" ni separadores de miles)'
    if formal >= needed and formal > shorthand * 2:
        return 'con signo de pesos, ej. "$35.000"'
    return ''


def _detect_punctuation_style(texts: list[str]) -> str:
    notes: list[str] = []
    questions = [text for text in texts if '?' in text]
    if questions:
        spaced = sum(1 for text in questions if ' ?' in text)
        opening = sum(1 for text in questions if '¿' in text)
        if spaced / len(questions) >= 0.6:
            notes.append('deja un espacio antes del signo de pregunta ("Que color quieres ?")')
        if opening / len(questions) <= 0.2:
            notes.append('casi nunca abre preguntas con "¿"')
    enders = [text for text in texts if len(text.split()) >= 3]
    if enders:
        with_period = sum(1 for text in enders if text.rstrip().endswith('.'))
        if with_period / len(enders) <= 0.15:
            notes.append('sin punto final en los mensajes')
    return '; '.join(notes)


def _detect_signature_phrases(texts: list[str]) -> list[str]:
    """Short acknowledgements the brand repeats ('dale', 'listo', 'okis')."""
    counts: Counter = Counter()
    for text in texts:
        stripped = _EMOJI_RE.sub('', text).strip().strip('!.,')
        words = stripped.split()
        if 1 <= len(words) <= 2 and len(stripped) <= 16:
            normalized = stripped.lower().strip('?¿ ')
            if (
                normalized
                and any(ch.isalpha() for ch in normalized)
                and not normalized.startswith(_GREETING_TOKENS)
                and not any(ch.isdigit() for ch in normalized)
                and not _contains_pii(normalized)
            ):
                counts[normalized] += 1
    return [phrase for phrase, count in counts.most_common(6) if count >= 2]


def _detect_greeting_style(conversations: list[dict]) -> str:
    greetings: Counter = Counter()
    for conversation in conversations:
        for message in conversation['messages']:
            if not message.get('is_brand') or _is_noise(message.get('text') or ''):
                continue
            text = message['text'].strip()
            if text.lower().startswith(_GREETING_TOKENS) and len(text.split()) <= 5 and not _contains_pii(text):
                greetings[text] += 1
            break  # only the brand's first text message per conversation
    top = [greeting for greeting, _count in greetings.most_common(2)]
    return ' / '.join(top)


def _select_voice_examples(texts: list[str], max_examples: int = 12) -> list[str]:
    """
    Pick short, PII-free real brand messages for few-shot, spread across
    what a seller actually says: greetings, prices, questions, closes.
    """
    candidates: list[str] = []
    seen: set[str] = set()
    for text in texts:
        words = len(text.split())
        if words < 2 or words > 14:
            continue
        if _contains_pii(text) or _is_noise(text):
            continue
        normalized = re.sub(r'\s+', ' ', text.lower()).strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(text)

    def _bucket(text: str) -> str:
        lowered = text.lower()
        if lowered.startswith(_GREETING_TOKENS):
            return 'greeting'
        if _PRICE_SHORTHAND_RE.search(text) or _PRICE_FORMAL_RE.search(text):
            return 'price'
        if '?' in text:
            return 'question'
        return 'other'

    buckets: dict[str, list[str]] = {'greeting': [], 'price': [], 'question': [], 'other': []}
    for text in candidates:
        buckets[_bucket(text)].append(text)

    quotas = {'greeting': 2, 'price': 3, 'question': 4, 'other': 3}
    selected: list[str] = []
    for bucket, quota in quotas.items():
        selected.extend(buckets[bucket][:quota])
    for text in candidates:
        if len(selected) >= max_examples:
            break
        if text not in selected:
            selected.append(text)
    return selected[:max_examples]


# ──────────────────────────────────────────────────────────────────────────────
# Continuous voice learning (from the org's own inbox, no export needed)
# ──────────────────────────────────────────────────────────────────────────────

def compile_voice_card_from_org_messages(organization, *, days: int = 90, max_messages: int = 500) -> dict:
    """
    Compile the voice card from HUMAN-authored inbox messages (role='agent'):
    what real people at the brand typed to real customers. Bot messages are
    deliberately excluded — learning voice from the bot's own output would be
    a feedback loop. Same output shape as compile_voice_card.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.conversations.models import Message

    cutoff = timezone.now() - timedelta(days=days)
    rows = list(
        Message.objects
        .filter(
            conversation__organization=organization,
            role__in=('user', 'agent'),
            timestamp__gte=cutoff,
        )
        .order_by('conversation_id', 'timestamp')
        .values('conversation_id', 'role', 'content')[:max_messages]
    )
    conversations: list[dict] = []
    current_id = None
    for row in rows:
        if row['conversation_id'] != current_id:
            current_id = row['conversation_id']
            conversations.append({'name': str(current_id), 'messages': []})
        conversations[-1]['messages'].append({
            'sender': row['role'],
            'text': str(row['content'] or ''),
            'is_brand': row['role'] == 'agent',
        })
    return compile_voice_card(conversations)


def apply_voice_to_settings(organization, voice_card: dict, voice_examples: list[str], *, source: str = 'imported') -> bool:
    """
    Merge a compiled voice_card + voice_examples into the org's onboarding
    settings (both v1 and v2 blob layouts). Never overwrites a card the user
    edited by hand (source='manual'). Returns True when settings changed.
    """
    from apps.channels_config.models import ChannelConfig

    config, _created = ChannelConfig.objects.get_or_create(
        organization=organization,
        channel='onboarding',
        defaults={'is_active': True, 'settings': {'settings_version': 2}},
    )
    settings_blob = dict(config.settings or {})
    if settings_blob.get('settings_version') == 2:
        container = settings_blob.setdefault('org_profile', {})
        brand = dict(container.get('brand') or {})
    else:
        # v1 blobs keep the brand under brand_profile (see settings_schema._v1_to_v2)
        container = settings_blob
        brand = dict(container.get('brand_profile') or {})

    existing_card = brand.get('voice_card') or {}
    if isinstance(existing_card, dict) and existing_card.get('source') == 'manual':
        logger.info('Voice card for %s is manual — not overwriting', organization.id)
        return False

    brand['voice_card'] = {**voice_card, 'source': source}
    existing_examples = [item for item in (brand.get('voice_examples') or []) if str(item).strip()]
    brand['voice_examples'] = merge_voice_examples(existing_examples, voice_examples)

    if settings_blob.get('settings_version') == 2:
        container['brand'] = brand
        settings_blob['org_profile'] = container
    else:
        settings_blob['brand_profile'] = brand
    config.settings = settings_blob
    config.save(update_fields=['settings', 'updated_at'])
    return True


def merge_voice_examples(existing: list[str], imported: list[str], cap: int = 12) -> list[str]:
    """Imported (measured) examples win slots over older ones; dedupe soft."""
    merged: list[str] = []
    seen: set[str] = set()
    for item in list(imported) + list(existing):
        normalized = ' '.join(str(item).lower().split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            merged.append(str(item).strip())
    return merged[:cap]


# ──────────────────────────────────────────────────────────────────────────────
# Example exchanges for the ExampleBank
# ──────────────────────────────────────────────────────────────────────────────

def seed_example_candidates(organization, exchanges: list[dict], *, origin: str = 'inbox_import') -> int:
    """
    Persist customer→brand exchanges as approved conversation_example
    LearningCandidates so the ExampleBank retrieves them as few-shot.
    Exchanges with PII never get stored (re-checked here so API callers
    can't sneak one past the compiler). Returns the number created.
    """
    import hashlib

    from apps.analytics.models import LearningCandidate

    created = 0
    for exchange in exchanges:
        question = str(exchange.get('question') or '').strip()[:220]
        answer = str(exchange.get('answer') or '').strip()[:400]
        if not question or not answer:
            continue
        if _contains_pii(question) or _contains_pii(answer):
            continue
        fingerprint = hashlib.sha256(f'{question}|{answer}'.encode('utf-8')).hexdigest()[:64]
        _obj, was_created = LearningCandidate.objects.update_or_create(
            organization=organization,
            kind='conversation_example',
            fingerprint=fingerprint,
            defaults={
                'status': 'approved',
                'title': question[:255],
                'source_question': question,
                'proposed_answer': answer,
                'confidence': 0.75,
                'metadata': {'origin': origin},
            },
        )
        created += 1 if was_created else 0
    return created


def select_example_exchanges(conversations: list[dict], max_exchanges: int = 20) -> list[dict]:
    """
    Extract customer-question → brand-reply pairs suitable as approved
    LearningCandidates (kind=conversation_example). The brand reply keeps its
    burst structure joined with newlines so the rhythm is visible to the LLM.
    PII on either side disqualifies the pair.
    """
    exchanges: list[dict] = []
    seen_questions: set[str] = set()
    for conversation in conversations:
        messages = conversation['messages']
        for index, message in enumerate(messages):
            if message.get('is_brand') or _is_noise(message.get('text') or ''):
                continue
            question = message['text'].strip()
            if len(question.split()) < 2 or _contains_pii(question):
                continue
            # Collect the brand's burst reply right after this message.
            reply_parts: list[str] = []
            for following in messages[index + 1:]:
                if not following.get('is_brand'):
                    break
                if _is_noise(following.get('text') or ''):
                    continue
                reply_parts.append(following['text'].strip())
                if len(reply_parts) >= 4:
                    break
            answer = '\n'.join(part for part in reply_parts if part).strip()
            if not answer or _contains_pii(answer):
                continue
            normalized = re.sub(r'\s+', ' ', question.lower()).strip()
            if normalized in seen_questions:
                continue
            seen_questions.add(normalized)
            exchanges.append({'question': question[:220], 'answer': answer[:400]})
            if len(exchanges) >= max_exchanges:
                return exchanges
    return exchanges
