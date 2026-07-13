"""
Customer History Service — cross-conversation order memory.

When a contact closes a conversation and later opens a NEW one (a fresh
Conversation row, e.g. a new WhatsApp thread or a new widget session) and
refers back to a past order, the sales agent otherwise starts from a blank
slate: SalesSession is one-per-conversation, so nothing about prior orders
carries over automatically.

Deliberately NOT an LLM-generated summary of past chats: Order rows already
hold the exact structured truth (order_number, items, total, status), so we
format them directly. This is cheap (a single indexed query on `contact`,
capped to a few rows) and grounded — the agent is handed real numbers it
already knows, instead of being asked to recall or summarize them.
"""
from typing import Optional


class CustomerHistoryService:
    STATUS_LABELS = {
        'new': 'pendiente',
        'paid': 'pagado',
        'processing': 'en proceso',
        'shipped': 'enviado',
        'delivered': 'entregado',
        'cancelled': 'cancelado',
    }

    @staticmethod
    def display_order_number(order) -> str:
        """
        Same derivation used at order-confirmation time (see
        `_create_guest_checkout_order`): the short hex prefix of the order's
        UUID is the ONLY order number the customer ever saw in chat — the
        model's own `order_number` counter field isn't set on this flow.
        """
        return str(order.id).split('-')[0].upper()

    @staticmethod
    def fetch(*, organization, contact, exclude_conversation_id=None, max_orders: int = 3) -> dict:
        """
        Returns {'text': formatted context block or '', 'totals': [float, ...]}.

        `totals` is meant to be merged into the price-hallucination guard's
        known-good list, so mentioning a past order's total is never flagged
        as an invented price just because it doesn't match the current cart.
        """
        if contact is None:
            return {'text': '', 'totals': []}
        # Anonymous placeholder contacts (no email/phone yet) can't have a
        # stable identity across conversations — skip the query entirely.
        if not (contact.email or contact.telefono):
            return {'text': '', 'totals': []}

        from apps.ecommerce.models import Order

        qs = Order.objects.filter(organization=organization, contact=contact)
        if exclude_conversation_id:
            qs = qs.exclude(conversation_id=exclude_conversation_id)
        orders = list(
            qs.order_by('-created_at')
            .only('id', 'items', 'total', 'status', 'payment_method', 'created_at')[:max_orders]
        )
        if not orders:
            return {'text': '', 'totals': []}

        lines = ['## Historial de pedidos de este cliente (datos reales, no inventes otros numeros)']
        totals = []
        for order in orders:
            items = order.items or []
            items_text = ', '.join(
                f"{item.get('title', 'producto')} x{item.get('qty', 1)}" for item in items[:3]
            ) or 'sin detalle'
            status_label = CustomerHistoryService.STATUS_LABELS.get(order.status, order.status)
            date_label = order.created_at.strftime('%Y-%m-%d') if order.created_at else ''
            order_ref = CustomerHistoryService.display_order_number(order)
            lines.append(
                f'- Pedido #{order_ref} ({date_label}): {items_text} - '
                f'${int(order.total):,} COP - {status_label} - pago: {order.payment_method or "no definido"}'
            )
            totals.append(float(order.total))
        lines.append('')
        return {'text': '\n'.join(lines), 'totals': totals}
