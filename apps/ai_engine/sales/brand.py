"""
Brand Voice — Converts the org's brand profile, sales playbook, buyer model
and commerce rules (settings_schema v2) into system-prompt sections so the
Sales Agent sounds like the brand itself and sells like a real salesperson.

The settings blob already captures all of this via onboarding; this module is
the bridge that puts it in front of the LLM on every turn.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class BrandVoice:
    """
    Builds prompt sections from the normalized runtime config
    (see apps.channels_config.settings_schema.normalise_settings).
    All methods tolerate partial/empty configs and return [] when
    there is nothing useful to say.
    """

    @staticmethod
    def load_runtime_config(organization) -> dict:
        """Load and normalise the org's onboarding settings blob."""
        try:
            from apps.channels_config.models import ChannelConfig
            from apps.channels_config.settings_schema import normalise_settings

            config = (
                ChannelConfig.objects
                .filter(organization=organization, channel='onboarding')
                .only('settings')
                .first()
            )
            return normalise_settings((config.settings or {}) if config else {})
        except Exception as exc:
            logger.warning('Failed to load sales agent runtime config: %s', exc)
            return {}

    # ── Prompt sections ───────────────────────────────────────────────────────

    @staticmethod
    def identity_lines(runtime_config: dict) -> list[str]:
        """'## Identidad comercial' — who the seller is and how the brand talks."""
        sales_agent = (runtime_config or {}).get('sales_agent') or {}
        org_profile = (runtime_config or {}).get('org_profile') or {}
        brand = org_profile.get('brand') or {}

        lines: list[str] = []
        business_parts = []
        if org_profile.get('what_you_sell'):
            business_parts.append(f'Vendes: {org_profile["what_you_sell"]}')
        if org_profile.get('who_you_sell_to'):
            business_parts.append(f'Cliente tipico: {org_profile["who_you_sell_to"]}')
        if business_parts:
            lines.append('. '.join(business_parts) + '.')

        if sales_agent.get('persona'):
            lines.append(f'Personalidad del agente: {sales_agent["persona"]}')
        if sales_agent.get('mission_statement'):
            lines.append(f'Mision comercial: {sales_agent["mission_statement"]}')
        if brand.get('brand_personality'):
            lines.append(f'Personalidad de la marca: {brand["brand_personality"]}')
        if brand.get('tone_of_voice'):
            lines.append(f'Tono de voz: {brand["tone_of_voice"]}')
        if brand.get('formality_level'):
            lines.append(f'Nivel de formalidad: {brand["formality_level"]}')
        if brand.get('value_proposition'):
            lines.append(f'Propuesta de valor: {brand["value_proposition"]}')
        if brand.get('key_differentiators'):
            lines.append(
                f'Diferenciadores clave: {", ".join((brand.get("key_differentiators") or [])[:4])}'
            )
        if brand.get('recommended_phrases'):
            lines.append(
                'Frases propias de la marca (usalas cuando suenen naturales): '
                + ', '.join((brand.get('recommended_phrases') or [])[:6])
            )
        if brand.get('avoid_phrases'):
            lines.append(
                f'Frases a evitar: {", ".join((brand.get("avoid_phrases") or [])[:6])}'
            )
        if brand.get('customer_style_notes'):
            lines.append(f'Notas de estilo con clientes: {brand["customer_style_notes"]}')
        if sales_agent.get('competitor_response'):
            lines.append(f'Si comparan con otras marcas: {sales_agent["competitor_response"]}')

        if not lines:
            return []
        return [
            '## Identidad comercial',
            'Hablas EN NOMBRE de la marca, no como un bot generico. Encarna esta identidad en cada frase:',
            *lines,
            '',
        ]

    @staticmethod
    def voice_example_lines(runtime_config: dict) -> list[str]:
        """'## Asi escribe la marca' — real sample messages the LLM must imitate.

        Few-shot voice: examples beat descriptions for style transfer. Seeded
        from onboarding; the learning loop will later refresh them with real
        high-performing messages.
        """
        brand = ((runtime_config or {}).get('org_profile') or {}).get('brand') or {}
        examples = [
            str(item).strip() for item in (brand.get('voice_examples') or [])
            if str(item).strip()
        ]
        if not examples:
            return []

        lines = [
            '## Asi escribe la marca (imita este estilo)',
            'Estos son mensajes reales de la marca. Copia su ritmo, vocabulario y calidez,',
            'NO su contenido: los productos y precios validos son solo los de este prompt.',
        ]
        lines += [f'- "{example[:280]}"' for example in examples[:6]]
        lines.append('')
        return lines

    @staticmethod
    def conversational_style_lines(runtime_config: dict) -> list[str]:
        """'## Estilo conversacional humano' — anti-robotic style guidance.

        Adapts to the brand's formality: a premium/formal brand must NOT be told
        to use street colloquialisms, and a casual brand must not sound stiff.
        """
        base = [
            '## Estilo conversacional humano',
            '- Suena como una persona real por chat, no como un bot de plantilla.',
            '- Varia el ritmo: combina una frase corta con una explicacion breve cuando haga falta.',
            '- Evita repetir estructuras tipo: "Perfecto. [precio]. Si quieres comprar, dime metodo de pago".',
            '- No abras siempre con "Perfecto" o "Excelente"; alterna aperturas naturales.',
            '- Mantente claro y util: humano no significa ambiguo.',
        ]
        if BrandVoice._is_formal_brand(runtime_config):
            return base + [
                '- Registro cuidado y calido, como un asesor de una marca premium: impecable pero nunca acartonado.',
                '- Trata al cliente con cortesia consistente; nada de jerga callejera ni exceso de confianza.',
                '- Cuando hables de precio + cierre, hazlo con elegancia y claridad, sin presion.',
                '',
            ]
        return base + [
            '- Cercano y relajado: puedes usar frases cortas y coloquiales cuando encajen con el tono del cliente (ej: "te cuento", "dale", "de una").',
            '- No uses tono corporativo ni formal excesivo.',
            '- Cuando hables de precio + cierre, suena conversacional (ej: "vale...", "te lo dejo en...") sin perder claridad.',
            '',
        ]

    @staticmethod
    def _is_formal_brand(runtime_config: dict) -> bool:
        """Deterministic heuristic over the brand's free-text style fields."""
        brand = ((runtime_config or {}).get('org_profile') or {}).get('brand') or {}
        blob = ' '.join(
            str(brand.get(field) or '')
            for field in ('formality_level', 'tone_of_voice', 'brand_personality')
        ).lower()
        informal_markers = ('informal', 'relajado', 'cercano', 'juvenil', 'coloquial', 'casual', 'parcero')
        if any(marker in blob for marker in informal_markers):
            return False
        formal_markers = ('formal', 'elegante', 'lujo', 'premium', 'sobrio', 'exclusiv', 'sofisticad', 'profesional')
        return any(marker in blob for marker in formal_markers)

    @staticmethod
    def seller_directives(runtime_config: dict) -> list[str]:
        """'## Como vendes' — behave like a real (human) salesperson of this brand."""
        sales_agent = (runtime_config or {}).get('sales_agent') or {}
        brand = ((runtime_config or {}).get('org_profile') or {}).get('brand') or {}
        playbook = sales_agent.get('playbook') or {}
        buyer_model = sales_agent.get('buyer_model') or {}

        lines = [
            '## Como vendes (compórtate como un vendedor real)',
            '- Eres un vendedor experto de la marca, no un asistente informativo: tu objetivo en cada turno es avanzar la venta un paso.',
            '- Termina tus mensajes con una micro-accion concreta (una pregunta de cierre, una propuesta o el siguiente paso), salvo que el cliente solo pida un dato puntual.',
            '- Ante una objecion no te rindas al primer "no": respondela con un beneficio concreto y reencuadra el valor. Maximo UNA insistencia suave; si el cliente mantiene el no, respetalo.',
            '- Escucha antes de vender: usa lo que el cliente ya dijo (presupuesto, uso, gustos) en tu propuesta, como haria un buen vendedor de mostrador.',
        ]

        if playbook.get('objection_style'):
            lines.append(f'- Estilo para manejar objeciones: {playbook["objection_style"]}')
        common_objections = [
            item for item in (buyer_model.get('common_objections') or []) if str(item).strip()
        ]
        if common_objections:
            lines.append(
                'Objeciones frecuentes de nuestros clientes (anticipalas con naturalidad): '
                + '; '.join(common_objections[:4])
            )
        if playbook.get('upsell_style'):
            lines.append(
                f'- Cuando el cliente ya eligio un producto, sugiere complementos asi: {playbook["upsell_style"]}'
            )
        if brand.get('urgency_style'):
            lines.append(f'- Nivel de urgencia permitido: {brand["urgency_style"]}')
        if playbook.get('follow_up_style'):
            lines.append(f'- Estilo de seguimiento: {playbook["follow_up_style"]}')

        lines.append('')
        return lines

    @staticmethod
    def commerce_rule_lines(runtime_config: dict) -> list[str]:
        """Hard business limits — appended to the absolute-rules section."""
        sales_agent = (runtime_config or {}).get('sales_agent') or {}
        rules = sales_agent.get('commerce_rules') or {}

        lines: list[str] = []
        if rules.get('discount_policy'):
            lines.append(f'- Politica de descuentos (no la excedas NUNCA): {rules["discount_policy"]}')
        if rules.get('negotiation_policy'):
            lines.append(f'- Politica de negociacion: {rules["negotiation_policy"]}')
        if rules.get('inventory_promise_rule'):
            lines.append(f'- Promesas de inventario: {rules["inventory_promise_rule"]}')
        if rules.get('delivery_promise_rule'):
            lines.append(f'- Promesas de entrega: {rules["delivery_promise_rule"]}')
        if rules.get('return_policy_summary'):
            lines.append(f'- Politica de devoluciones: {rules["return_policy_summary"]}')

        forbidden = [
            item for item in (
                (rules.get('forbidden_claims') or []) + (rules.get('forbidden_promises') or [])
            )
            if str(item).strip()
        ]
        if forbidden:
            lines.append(
                '- PROHIBIDO afirmar o prometer: ' + '; '.join(forbidden[:6])
            )
        return lines

    @staticmethod
    def strategy_guidance(strategy: str, runtime_config: dict) -> str:
        """Base strategy guidance, enriched with the brand's playbook style."""
        sales_agent = (runtime_config or {}).get('sales_agent') or {}
        brand = ((runtime_config or {}).get('org_profile') or {}).get('brand') or {}
        playbook = sales_agent.get('playbook') or {}

        base = {
            'discover': 'Muestra 1-2 productos disponibles del catalogo. Si el cliente dio preferencias, muestra los que mas encajan.',
            'recommend': 'Recomienda 1-2 productos SOLO del listado de productos disponibles. Si la busqueda es ambigua, pide confirmacion en vez de asumir.',
            'close': 'Enfocate en cerrar la venta. Pregunta si quiere proceder.',
            'inform': 'Da la informacion solicitada de forma clara y concisa.',
            'clarify': 'Haz UNA sola pregunta para entender mejor que necesita.',
            'redirect': 'En una oracion, explica que solo puedes ayudar con los productos de la tienda.',
        }
        style_for_strategy = {
            'discover': playbook.get('opening_style'),
            'recommend': playbook.get('recommendation_style'),
            'close': playbook.get('closing_style') or brand.get('preferred_closing_style'),
        }

        guidance = base.get(strategy, '')
        style = str(style_for_strategy.get(strategy) or '').strip()
        if style:
            guidance = f'{guidance} Estilo de la marca para este momento: {style}'.strip()
        return guidance

    # ── Deterministic guard for the validator ─────────────────────────────────

    @staticmethod
    def brand_guard(runtime_config: dict) -> dict:
        """Phrases the response must never contain — enforced post-generation."""
        sales_agent = (runtime_config or {}).get('sales_agent') or {}
        brand = ((runtime_config or {}).get('org_profile') or {}).get('brand') or {}
        rules = sales_agent.get('commerce_rules') or {}

        def _clean(values) -> list[str]:
            return [str(item).strip() for item in (values or []) if str(item).strip()]

        return {
            'avoid_phrases': _clean(brand.get('avoid_phrases')),
            'forbidden_claims': _clean(rules.get('forbidden_claims')) + _clean(rules.get('forbidden_promises')),
        }
