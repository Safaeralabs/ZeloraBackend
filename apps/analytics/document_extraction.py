import hashlib
import re

from apps.analytics.models import DocumentExtractionCandidate


HEADING_RE = re.compile(r'^[A-Z0-9][A-Z0-9\s"()./%:-]{4,}$')
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
        if HEADING_RE.match(line) and len(line) <= 90:
            current_heading = line.title()
            if len(current_heading.split()) <= 8:
                candidates.append({
                    'kind': 'service',
                    'title': current_heading,
                    'body': '',
                    'confidence': 0.62,
                    'metadata': {'source': 'heading'},
                })
            continue
        if current_heading and len(line) <= 80 and not PRICE_RE.search(line) and not POLICY_HINT_RE.search(line):
            if len(line.split()) <= 8:
                candidates.append({
                    'kind': 'service',
                    'title': line,
                    'body': f'Detectado dentro de la seccion {current_heading}.',
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
    }.get(candidate.kind, 'document_extraction')
    category = {
        'pricing_rule': 'Reglas de precio',
        'policy': 'Politicas y condiciones',
        'flow_hint': 'Flow hints',
    }.get(candidate.kind, 'Documento estructurado')
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
        tags=[tag, 'document_extraction'],
        status='draft',
    )
    candidate.status = 'approved'
    candidate.approved_article = article
    candidate.save(update_fields=['status', 'approved_article', 'updated_at'])
    return {'target': 'article', 'id': str(article.id)}
