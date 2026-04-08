import hashlib
import re
import structlog

from apps.analytics.models import DocumentExtractionCandidate

logger = structlog.get_logger(__name__)


# Matches all-caps headings OR Title Case short lines (≤ 8 words, no sentence-ending punctuation)
HEADING_RE = re.compile(r'^[A-Z0-9][A-Z0-9\s"()./%:-]{4,}$')
TITLE_CASE_RE = re.compile(r'^[A-ZÁÉÍÓÚÑ][^\n.!?]{3,60}$')
PRICE_RE = re.compile(r'(\$\s?\d[\d.,]*|\b\d+(?:[.,]\d+)?%\b|\bdesde\s+\$\s?\d[\d.,]*)', re.IGNORECASE)
POLICY_HINT_RE = re.compile(
    r'\b(requiere|debe|aplica|incluye|no se permite|no se permiten|presentar|reserva|anticipo|recargo|subsidio)\b',
    re.IGNORECASE,
)
FLOW_HINT_RE = re.compile(
    r'\b(categoria|categor[ií]a|afiliado|afiliaci[oó]n|horas|duraci[oó]n|evento|edad|paquete|modalidad|tipo)\b',
    re.IGNORECASE,
)


def _clean_line(value: str) -> str:
    return re.sub(r'\s+', ' ', (value or '').strip())


def _make_fingerprint(document_id: str, kind: str, title: str, body: str) -> str:
    base = f'{document_id}:{kind}:{title.strip().lower()}:{body.strip().lower()}'
    return hashlib.sha256(base.encode('utf-8')).hexdigest()


def _iter_meaningful_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in (text or '').splitlines():
        line = _clean_line(raw.strip(' -*•\t'))
        if len(line) < 3:
            continue
        if line.lower() in {'servicios', 'condiciones', 'precios', 'incluye', 'resumen general'}:
            continue
        lines.append(line)
    return lines


def _infer_service_candidates(lines: list[str]) -> list[dict]:
    candidates: list[dict] = []
    current_heading = ''
    for line in lines:
        is_allcaps_heading = bool(HEADING_RE.match(line)) and len(line) <= 90
        is_title_heading = (
            bool(TITLE_CASE_RE.match(line))
            and len(line.split()) <= 8
            and not PRICE_RE.search(line)
            and not POLICY_HINT_RE.search(line)
        )
        if is_allcaps_heading or is_title_heading:
            current_heading = line.title()
            candidates.append({
                'kind': 'service',
                'title': current_heading,
                'body': '',
                'confidence': 0.65,
                'metadata': {'source': 'heading'},
            })
            continue
        if current_heading and len(line) <= 120 and not PRICE_RE.search(line) and not POLICY_HINT_RE.search(line):
            if len(line.split()) <= 12:
                candidates.append({
                    'kind': 'service',
                    'title': line,
                    'body': f'Detectado dentro de la sección: {current_heading}.',
                    'confidence': 0.68,
                    'metadata': {'source': 'section_item', 'section': current_heading},
                })
    return candidates


def _infer_pricing_candidates(lines: list[str]) -> list[dict]:
    candidates: list[dict] = []
    for line in lines:
        if PRICE_RE.search(line):
            title = line[:120]
            confidence = 0.7 if '$' in line or '%' in line else 0.58
            candidates.append({
                'kind': 'pricing_rule',
                'title': title,
                'body': line,
                'confidence': confidence,
                'metadata': {'detected_prices': PRICE_RE.findall(line)},
            })
    return candidates


def _infer_policy_candidates(lines: list[str]) -> list[dict]:
    candidates: list[dict] = []
    for line in lines:
        if POLICY_HINT_RE.search(line):
            candidates.append({
                'kind': 'policy',
                'title': line[:120],
                'body': line,
                'confidence': 0.66,
                'metadata': {},
            })
    return candidates


def _infer_flow_hints(lines: list[str]) -> list[dict]:
    prompts: list[dict] = []
    for line in lines:
        if FLOW_HINT_RE.search(line) and (PRICE_RE.search(line) or POLICY_HINT_RE.search(line)):
            prompts.append({
                'kind': 'flow_hint',
                'title': f'Preguntas sugeridas: {line[:80]}',
                'body': line,
                'confidence': 0.63,
                'metadata': {
                    'suggested_questions': _suggest_questions_from_line(line),
                },
            })
    return prompts


def _suggest_questions_from_line(line: str) -> list[str]:
    mapping = [
        ('afili', 'Eres afiliado, empresa afiliada o particular?'),
        ('categor', 'Si la conoces, cual es tu categoria A, B o C?'),
        ('hora', 'Cuantas horas necesitas?'),
        ('duraci', 'Que duracion necesitas?'),
        ('evento', 'Que tipo de evento o uso tendra?'),
        ('edad', 'Que edad tiene la persona beneficiaria?'),
        ('paquete', 'Quieres paquete de 2, 3 o 5 unidades?'),
        ('modalidad', 'Prefieres modalidad presencial, remota o hibrida?'),
        ('tipo', 'Que tipo necesitas exactamente?'),
    ]
    lowered = line.lower()
    questions = [question for needle, question in mapping if needle in lowered]
    return questions[:5]


def generate_document_extraction_candidates(*, document) -> dict[str, int]:
    text = (document.extracted_text or '').strip()
    if not text:
        return {'created': 0, 'updated': 0, 'processed_documents': 1}

    lines = _iter_meaningful_lines(text[:40000])
    raw_candidates = [
        *_infer_service_candidates(lines),
        *_infer_pricing_candidates(lines),
        *_infer_policy_candidates(lines),
        *_infer_flow_hints(lines),
    ]

    created = 0
    updated = 0
    seen: set[tuple[str, str, str]] = set()
    for item in raw_candidates[:250]:
        title = _clean_line(item['title'])[:255]
        body = _clean_line(item.get('body', ''))[:3000]
        if not title:
            continue
        dedupe_key = (item['kind'], title.lower(), body.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        fingerprint = _make_fingerprint(str(document.id), item['kind'], title, body)
        candidate, was_created = DocumentExtractionCandidate.objects.update_or_create(
            organization=document.organization,
            kind=item['kind'],
            fingerprint=fingerprint,
            defaults={
                'source_document': document,
                'title': title,
                'body': body,
                'confidence': item.get('confidence', 0.55),
                'metadata': item.get('metadata', {}),
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return {'created': created, 'updated': updated, 'processed_documents': 1}


def generate_ai_analysis_candidates(*, document, settings=None) -> dict[str, int]:
    """
    Run AI-powered analysis on a KB document using OpenAI.
    Produces candidates of kind 'ai_summary' and 'ai_qa'.
    Silently skips if ENABLE_REAL_AI is False or no API key.
    """
    if settings is None:
        from django.conf import settings as django_settings
        settings = django_settings

    text = (document.extracted_text or '').strip()
    if not text:
        return {'created': 0, 'updated': 0}

    if not getattr(settings, 'ENABLE_REAL_AI', False) or not getattr(settings, 'OPENAI_API_KEY', ''):
        return {'created': 0, 'updated': 0}

    doc_id = str(document.id)
    logger.info('ai_analysis_start', doc_id=doc_id, filename=document.filename, text_len=len(text))

    try:
        import json
        import openai
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

        system_prompt = (
            'Eres un asistente que analiza documentos de empresa para extraer conocimiento útil. '
            'Responde SIEMPRE en JSON válido, sin texto adicional.'
        )
        user_prompt = (
            'Analiza el siguiente documento de empresa y devuelve un JSON con esta estructura exacta:\n'
            '{\n'
            '  "summary": "Resumen claro en 2-3 oraciones de qué trata el documento",\n'
            '  "purpose": "faq|policy|business",\n'
            '  "services": [\n'
            '    {"name": "Nombre del servicio o producto", "description": "Descripción breve de qué incluye, para qué sirve, precio si aparece"}\n'
            '  ],\n'
            '  "faqs": [\n'
            '    {"question": "Pregunta frecuente sobre el servicio", "answer": "Respuesta concreta"}\n'
            '  ],\n'
            '  "policies": [\n'
            '    {"title": "Nombre de la política o condición", "body": "Texto exacto de la política"}\n'
            '  ],\n'
            '  "flow_hints": [\n'
            '    {"title": "Nombre del flujo sugerido", "body": "Por qué este documento sugiere este flujo"}\n'
            '  ]\n'
            '}\n\n'
            'Reglas:\n'
            '- services: lista TODOS los servicios, productos, paquetes o planes que aparezcan en el documento. Si el documento es un catálogo, lista cada ítem.\n'
            '- faqs: 3 a 7 preguntas reales que un cliente haría sobre el contenido.\n'
            '- policies: condiciones, restricciones, requisitos, formas de pago, devoluciones, etc.\n'
            '- flow_hints: solo si el documento sugiere flujos conversacionales claros (e.g. "para cotizar X el cliente debe responder Y").\n'
            '- Si una sección no aplica, devuelve lista vacía [].\n\n'
            f'DOCUMENTO:\n{text[:7000]}'
        )

        completion = client.chat.completions.create(
            model=getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini'),
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            max_tokens=2500,
            temperature=0.3,
            response_format={'type': 'json_object'},
        )

        raw = completion.choices[0].message.content or '{}'
        logger.info(
            'ai_analysis_raw_response',
            doc_id=doc_id,
            raw_len=len(raw),
            raw_preview=raw[:500],
        )
        data = json.loads(raw)
        logger.info(
            'ai_analysis_parsed',
            doc_id=doc_id,
            summary_len=len(data.get('summary') or ''),
            services_count=len(data.get('services') or []),
            faqs_count=len(data.get('faqs') or []),
            policies_count=len(data.get('policies') or []),
            flow_hints_count=len(data.get('flow_hints') or []),
        )

    except Exception as exc:
        logger.error('ai_analysis_failed', doc_id=doc_id, error=str(exc), exc_info=True)
        return {'created': 0, 'updated': 0}

    created = 0
    updated = 0

    # ── ai_summary candidate ──────────────────────────────────────────────────
    summary = (data.get('summary') or '').strip()
    purpose = (data.get('purpose') or 'faq').strip()
    if summary:
        fingerprint = _make_fingerprint(str(document.id), 'ai_summary', summary[:80], '')
        _, was_created = DocumentExtractionCandidate.objects.update_or_create(
            organization=document.organization,
            kind='ai_summary',
            fingerprint=fingerprint,
            defaults={
                'source_document': document,
                'title': f'Resumen: {document.filename}',
                'body': summary,
                'confidence': 0.90,
                'metadata': {'purpose': purpose, 'source': 'openai'},
            },
        )
        created += 1 if was_created else 0
        updated += 0 if was_created else 1

    # ── ai_qa candidates ──────────────────────────────────────────────────────
    faqs = data.get('faqs') or []
    for faq in faqs[:10]:
        question = _clean_line(faq.get('question') or '')
        answer = _clean_line(faq.get('answer') or '')
        if not question or not answer:
            continue
        fingerprint = _make_fingerprint(str(document.id), 'ai_qa', question, answer[:100])
        _, was_created = DocumentExtractionCandidate.objects.update_or_create(
            organization=document.organization,
            kind='ai_qa',
            fingerprint=fingerprint,
            defaults={
                'source_document': document,
                'title': question[:255],
                'body': answer[:3000],
                'confidence': 0.85,
                'metadata': {'source': 'openai', 'purpose': purpose},
            },
        )
        created += 1 if was_created else 0
        updated += 0 if was_created else 1

    # ── service candidates (AI-extracted) ────────────────────────────────────
    services = data.get('services') or []
    for svc in services[:30]:
        name = _clean_line(svc.get('name') or '')
        description = _clean_line(svc.get('description') or '')
        if not name:
            continue
        fingerprint = _make_fingerprint(str(document.id), 'service', name, description[:80])
        _, was_created = DocumentExtractionCandidate.objects.update_or_create(
            organization=document.organization,
            kind='service',
            fingerprint=fingerprint,
            defaults={
                'source_document': document,
                'title': name[:255],
                'body': description[:3000],
                'confidence': 0.88,
                'metadata': {'source': 'openai'},
            },
        )
        created += 1 if was_created else 0
        updated += 0 if was_created else 1

    # ── policy candidates (AI-extracted) ──────────────────────────────────────
    policies = data.get('policies') or []
    for pol in policies[:15]:
        title = _clean_line(pol.get('title') or '')
        body = _clean_line(pol.get('body') or '')
        if not title:
            continue
        fingerprint = _make_fingerprint(str(document.id), 'policy', title, body[:80])
        _, was_created = DocumentExtractionCandidate.objects.update_or_create(
            organization=document.organization,
            kind='policy',
            fingerprint=fingerprint,
            defaults={
                'source_document': document,
                'title': title[:255],
                'body': body[:3000],
                'confidence': 0.87,
                'metadata': {'source': 'openai'},
            },
        )
        created += 1 if was_created else 0
        updated += 0 if was_created else 1

    # ── flow_hint candidates (AI-extracted) ───────────────────────────────────
    flow_hints = data.get('flow_hints') or []
    for hint in flow_hints[:10]:
        title = _clean_line(hint.get('title') or '')
        body = _clean_line(hint.get('body') or '')
        if not title:
            continue
        fingerprint = _make_fingerprint(str(document.id), 'flow_hint', title, body[:80])
        _, was_created = DocumentExtractionCandidate.objects.update_or_create(
            organization=document.organization,
            kind='flow_hint',
            fingerprint=fingerprint,
            defaults={
                'source_document': document,
                'title': title[:255],
                'body': body[:3000],
                'confidence': 0.80,
                'metadata': {'source': 'openai'},
            },
        )
        created += 1 if was_created else 0
        updated += 0 if was_created else 1

    return {'created': created, 'updated': updated}


def approve_document_extraction_candidate(*, candidate, author=None):
    from apps.ecommerce.models import Product
    from apps.knowledge_base.models import KBArticle

    if candidate.kind == 'service':
        product = Product.objects.create(
            organization=candidate.organization,
            title=candidate.title,
            description=candidate.body,
            category='Servicio detectado',
            offer_type='service',
            price_type='quote_required',
            service_mode='onsite',
            requires_booking=True,
            requires_shipping=False,
            service_duration_minutes=60,
            attributes={
                'source': 'document_extraction',
                'document_id': str(candidate.source_document_id),
                **(candidate.metadata or {}),
            },
            status='draft',
            is_active=True,
        )
        candidate.status = 'approved'
        candidate.approved_product = product
        candidate.save(update_fields=['status', 'approved_product', 'updated_at'])
        return {'target': 'product', 'id': str(product.id)}

    tag = {
        'pricing_rule': 'pricing_rule',
        'policy': 'policy',
        'flow_hint': 'flow_hint',
        'ai_summary': 'ai_summary',
        'ai_qa': 'ai_qa',
    }.get(candidate.kind, 'document_extraction')
    category = {
        'pricing_rule': 'Reglas de precio',
        'policy': 'Politicas y condiciones',
        'flow_hint': 'Flow hints',
        'ai_summary': 'Resumen IA',
        'ai_qa': 'FAQ extraído por IA',
    }.get(candidate.kind, 'Documento estructurado')
    _PURPOSE_ALIAS = {
        'product_context': 'business', 'product': 'business', 'why_us': 'business',
        'pricing': 'policy',
        'objection': 'sales_scripts', 'closing': 'sales_scripts',
    }
    # Map extraction kind → KB purpose
    _KIND_PURPOSE = {
        'policy':        'policy',
        'pricing_rule':  'policy',
        'service':       'business',
        'flow_hint':     'faq',
        'ai_summary':    None,   # uses metadata purpose
        'ai_qa':         None,   # uses metadata purpose
    }
    if candidate.kind in _KIND_PURPOSE and _KIND_PURPOSE[candidate.kind] is not None:
        purpose = _KIND_PURPOSE[candidate.kind]
    else:
        raw_purpose = (candidate.metadata or {}).get('purpose', 'faq')
        purpose = _PURPOSE_ALIAS.get(raw_purpose, raw_purpose)

    content = candidate.body
    if candidate.kind == 'flow_hint' and candidate.metadata.get('suggested_questions'):
        questions = '\n'.join(f'- {question}' for question in candidate.metadata['suggested_questions'])
        content = f'{candidate.body}\n\nPreguntas sugeridas:\n{questions}'

    article = KBArticle.objects.create(
        organization=candidate.organization,
        author=author,
        title=candidate.title,
        content=content,
        category=category,
        purpose=purpose,
        tags=[tag, 'document_extraction'],
        status='draft',
    )
    candidate.status = 'approved'
    candidate.approved_article = article
    candidate.save(update_fields=['status', 'approved_article', 'updated_at'])
    return {'target': 'article', 'id': str(article.id)}
