"""
Order Lookup Service — lets the Sales Agent answer "what's the status of my
order?" when a customer types their order number in chat.

Security model (deliberate, do not loosen without re-reviewing):
- Read-only. This service only assembles text for the LLM prompt — it never
  mutates an Order. Cancel/modify requests must stay on authenticated
  staff-only endpoints (OrderViewSet), never be actioned from a chat message.
- Identity-gated detail. The order number alone is not a strong secret, so a
  requester whose resolved contact (phone/email on this conversation)
  doesn't match the order's contact only gets a generic status confirmation —
  never the address, items, phone, or total that the real owner would see.
"""
import re

from django.db.models import CharField
from django.db.models.functions import Cast

_ORDER_CODE_PATTERN = re.compile(r'\b[0-9A-Fa-f]{6,8}\b')

_STATUS_LABELS = {
    'new': 'pendiente de confirmar',
    'paid': 'pagado',
    'processing': 'en proceso',
    'shipped': 'enviado',
    'delivered': 'entregado',
    'cancelled': 'cancelado',
}


class OrderLookupService:
    @staticmethod
    def extract_code(text: str) -> str | None:
        """Best-effort: pulls a 6-8 char hex token that looks like an order code."""
        if not text:
            return None
        match = _ORDER_CODE_PATTERN.search(text)
        return match.group(0).upper() if match else None

    @staticmethod
    def find(*, organization, code: str):
        from apps.ecommerce.models import Order

        code = (code or '').strip().upper()
        if not code:
            return None
        return (
            Order.objects
            .annotate(id_text=Cast('id', CharField()))
            .filter(organization=organization, id_text__istartswith=code)
            .select_related('contact')
            .first()
        )

    @staticmethod
    def build_context(*, organization, message_text: str, requester_contact) -> dict:
        """
        Returns {'text': str, 'matched': bool}. Empty text when the message
        has no order-code-shaped token — cheap to call unconditionally.
        """
        code = OrderLookupService.extract_code(message_text)
        if not code:
            return {'text': '', 'matched': False}

        order = OrderLookupService.find(organization=organization, code=code)
        if not order:
            return {
                'text': (
                    '## Consulta de pedido\n'
                    f'El cliente menciono un numero de pedido ({code}) pero no existe ningun pedido con ese numero '
                    'en este negocio. Dile que no lo encuentras y pidele que confirme el numero. '
                    'No inventes un estado ni un pedido.\n'
                ),
                'matched': False,
            }

        identity_matches = bool(
            requester_contact
            and order.contact_id
            and order.contact_id == requester_contact.id
        )
        status_label = _STATUS_LABELS.get(order.status, order.status)
        order_ref = str(order.id).split('-')[0].upper()

        if identity_matches:
            items = order.items or []
            items_text = ', '.join(
                f"{item.get('title', 'producto')} x{item.get('qty', 1)}" for item in items[:5]
            ) or 'sin detalle'
            lines = [
                '## Consulta de pedido (identidad verificada — puedes dar el detalle completo)',
                f'- Pedido #{order_ref}: {items_text} - ${int(order.total):,} COP - estado: {status_label} '
                f'- pago: {order.payment_method or "no definido"}',
                'Responde la pregunta del cliente sobre ESTE pedido con estos datos reales. '
                'No inventes fecha de entrega si no la tienes. No puedes cancelar ni modificar el pedido desde aqui.',
            ]
        else:
            lines = [
                '## Consulta de pedido (identidad NO verificada)',
                f'- Existe un pedido #{order_ref} con estado: {status_label}.',
                'El telefono/correo de quien pregunta no coincide con el dueno de este pedido: '
                'SOLO confirma el estado general (pendiente/pagado/en proceso/enviado/entregado/cancelado). '
                'NUNCA reveles direccion, productos, telefono ni total de este pedido. '
                'Si pide mas detalle, dile que por seguridad debe escribirte desde el mismo numero o correo '
                'con el que hizo el pedido, o que lo puedes conectar con soporte humano para verificar su identidad.',
            ]

        return {'text': '\n'.join(lines), 'matched': True}
