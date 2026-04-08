from __future__ import annotations

import re

from .schemas import (
    IntentClassification,
    IntentName,
    NormalizedEvent,
    RiskAssessment,
    Sentiment,
    Urgency,
)


class IntentService:
    def classify(self, event: NormalizedEvent, risk: RiskAssessment) -> IntentClassification:
        text = (risk.sanitized_text or event.message_text).lower()

        if risk.level.value in ('high', 'critical'):
            return IntentClassification(
                intent=IntentName.PROMPT_INJECTION_ATTEMPT,
                confidence=0.99,
                entities={},
                sentiment=Sentiment.NEUTRAL,
                urgency=Urgency.HIGH,
                recommended_action='block_action',
            )

        if any(term in text for term in ('subsidio status', 'estado del subsidio', 'subsidio', 'subsidy status', 'subsidy')):
            return IntentClassification(
                intent=IntentName.CHECK_SUBSIDY,
                confidence=0.96,
                entities=self._extract_document_type(text),
                sentiment=Sentiment.NEUTRAL,
                urgency=Urgency.NORMAL,
                recommended_action='start_flow',
            )

        if any(term in text for term in ('certificado', 'certificate')):
            return IntentClassification(
                intent=IntentName.REQUEST_CERTIFICATE,
                confidence=0.95,
                entities=self._extract_document_type(text),
                sentiment=Sentiment.NEUTRAL,
                urgency=Urgency.NORMAL,
                recommended_action='start_flow',
            )

        if any(term in text for term in (
            'problema con mi afiliacion',
            'problemas con mi afiliacion',
            'problema con mi afiliación',
            'problemas con mi afiliación',
            'afiliacion',
            'afiliación',
            'beneficiario',
            'beneficiarios',
            'kit infantil',
            'cuota monetaria',
            'daviplata',
            'aportes',
        )):
            return IntentClassification(
                intent=IntentName.GENERAL_FAQ,
                confidence=0.91,
                entities={},
                sentiment=Sentiment.NEUTRAL,
                urgency=Urgency.NORMAL,
                recommended_action='route_to_operations_agent',
            )

        if any(term in text for term in ('appointment', 'book', 'agendar', 'reservar cita', 'cita')):
            return IntentClassification(
                intent=IntentName.BOOK_APPOINTMENT,
                confidence=0.95,
                entities=self._extract_time_window(text),
                sentiment=Sentiment.NEUTRAL,
                urgency=Urgency.NORMAL,
                recommended_action='start_flow',
            )

        if any(term in text for term in (
            'estado del pedido', 'donde esta mi pedido', 'dónde está mi pedido',
            'rastrear', 'tracking', 'numero de pedido', 'número de pedido', 'pedido numero',
            'mi orden', 'order status', 'where is my order',
        )):
            return IntentClassification(
                intent=IntentName.ORDER_STATUS,
                confidence=0.95,
                entities=self._extract_order_number(text),
                sentiment=Sentiment.NEUTRAL,
                urgency=Urgency.NORMAL,
                recommended_action='route_to_operations_agent',
            )

        if any(term in text for term in (
            'devolver', 'devolucion', 'reembolso', 'garantia',
            'cambio', 'quiero cambiar', 'product defect', 'no funciona', 'defectuoso',
        )):
            return IntentClassification(
                intent=IntentName.RETURN_REQUEST,
                confidence=0.94,
                entities=self._extract_order_number(text),
                sentiment=Sentiment.NEGATIVE,
                urgency=Urgency.HIGH,
                recommended_action='route_to_operations_agent',
            )

        if any(term in text for term in (
            'precio', 'cuanto cuesta', 'cuánto cuesta', 'cuánto vale', 'cuanto vale',
            'cost', 'price', 'tarifa', 'valor', 'cuánto es', 'cuanto es',
            'teatro akuaipaa', 'akuaipaa',
        )):
            return IntentClassification(
                intent=IntentName.PRICE_INQUIRY,
                confidence=0.93,
                entities={},
                sentiment=Sentiment.NEUTRAL,
                urgency=Urgency.NORMAL,
                recommended_action='route_to_sales_agent',
            )

        if any(term in text for term in (
            'comprar', 'buy', 'quiero', 'necesito', 'busco', 'estoy buscando', 'ando buscando', 'buscando', 'tienen',
            'disponible', 'disponibilidad', 'stock', 'availability',
            'me interesa', 'agregar al carrito', 'add to cart',
            'reservar teatro', 'alquilar teatro', 'alquilar auditorio', 'alquiler de espacios',
            'crecer sano', 'nutricion', 'nutrición', 'tecnico laboral', 'tecnico', 'técnico',
            'educacion informal', 'educación informal', 'teatro akuaipaa',
        )):
            return IntentClassification(
                intent=IntentName.BUY_INTENT,
                confidence=0.94,
                entities=self._extract_quantity(text),
                sentiment=Sentiment.POSITIVE,
                urgency=Urgency.NORMAL,
                recommended_action='route_to_sales_agent',
            )

        if any(term in text for term in (
            'producto', 'product', 'modelo', 'model', 'talla', 'size',
            'color', 'variante', 'especificaciones', 'specs', 'caracteristicas',
        )):
            return IntentClassification(
                intent=IntentName.PRODUCT_INQUIRY,
                confidence=0.88,
                entities={},
                sentiment=Sentiment.NEUTRAL,
                urgency=Urgency.NORMAL,
                recommended_action='route_to_sales_agent',
            )

        if any(term in text for term in (
            'horario', 'direccion', 'address', 'contacto',
            'telefono', 'como funciona', 'informacion',
            'ayuda', 'help', 'soporte', 'support',
        )):
            return IntentClassification(
                intent=IntentName.GENERAL_FAQ,
                confidence=0.80,
                entities={},
                sentiment=Sentiment.NEUTRAL,
                urgency=Urgency.NORMAL,
                recommended_action='direct_ai_reply',
            )

        # ── Org-specific custom intents ───────────────────────────────────────
        tenant_id = getattr(event, 'tenant_id', None)
        if tenant_id:
            try:
                from apps.flows.models import CustomIntent
                custom_intents = list(
                    CustomIntent.objects.filter(organization_id=tenant_id, is_active=True)
                )
                for ci in custom_intents:
                    kws = [k.lower().strip() for k in (ci.keywords or []) if k.strip()]
                    if kws and any(kw in text for kw in kws):
                        return IntentClassification(
                            intent=IntentName.UNKNOWN,
                            confidence=0.92,
                            entities={},
                            sentiment=Sentiment.NEUTRAL,
                            urgency=Urgency.NORMAL,
                            recommended_action='start_flow',
                            custom_intent_name=ci.name,
                        )
            except Exception:
                pass

        return IntentClassification(
            intent=IntentName.UNKNOWN,
            confidence=0.42,
            entities={},
            sentiment=Sentiment.NEUTRAL,
            urgency=Urgency.NORMAL,
            recommended_action='request_clarification',
        )

    def _extract_document_type(self, text: str) -> dict[str, str]:
        if ' cc ' in f' {text} ' or 'cedula' in text or 'cédula' in text:
            return {'document_type': 'cc'}
        if 'nit' in text:
            return {'document_type': 'nit'}
        return {}

    def _extract_quantity(self, text: str) -> dict[str, int]:
        match = re.search(r'\b(\d{1,4})\b', text)
        if match is None:
            return {}
        return {'quantity': int(match.group(1))}

    def _extract_time_window(self, text: str) -> dict[str, str]:
        if 'tomorrow' in text or 'mañana' in text or 'manana' in text:
            return {'requested_slot': 'tomorrow'}
        if 'today' in text or 'hoy' in text:
            return {'requested_slot': 'today'}
        return {}

    def _extract_order_number(self, text: str) -> dict[str, str]:
        match = re.search(r'\b([A-Z0-9]{6,20})\b', text.upper())
        if match:
            return {'order_number': match.group(1)}
        match = re.search(r'\b(\d{4,12})\b', text)
        if match:
            return {'order_number': match.group(1)}
        return {}
