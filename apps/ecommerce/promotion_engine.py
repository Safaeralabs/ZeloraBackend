from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.db.models import Q
from django.utils import timezone

from .models import Promotion


def _d(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal('0')


@dataclass
class _Line:
    product_id: str
    category: str
    qty: int
    unit_price: Decimal
    subtotal: Decimal
    discount: Decimal = Decimal('0')


class PromotionEngine:
    @staticmethod
    def evaluate_cart(
        *,
        organization,
        lines: Iterable[dict],
        shipping_amount: Decimal | float | int = 0,
        discount_code: str = '',
    ) -> dict:
        parsed_lines: list[_Line] = []
        for raw in list(lines or []):
            qty = max(1, int(raw.get('qty') or 1))
            unit = _d(raw.get('unit_price'))
            parsed_lines.append(
                _Line(
                    product_id=str(raw.get('product_id') or '').strip(),
                    category=str(raw.get('category') or '').strip(),
                    qty=qty,
                    unit_price=unit,
                    subtotal=unit * qty,
                )
            )
        subtotal = sum((line.subtotal for line in parsed_lines), Decimal('0'))
        if subtotal <= 0:
            return {
                'subtotal': 0.0,
                'discount_total': 0.0,
                'total': 0.0,
                'total_with_shipping': float(max(_d(shipping_amount), Decimal('0'))),
                'shipping_discount_total': 0.0,
                'applied_promotions': [],
                'line_items': [],
                'free_shipping': False,
            }

        now = timezone.now()
        promotions = (
            Promotion.objects.filter(organization=organization, is_active=True)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
            .distinct()
            .prefetch_related('products')
        )
        promos_sorted = sorted(
            promotions,
            key=lambda promo: (int(getattr(promo, 'priority', 100) or 100), promo.updated_at),
        )

        product_discount_total = Decimal('0')
        order_discount_total = Decimal('0')
        shipping_discount_total = Decimal('0')
        applied_promotions: list[dict] = []
        has_non_combinable = False
        normalized_code = str(discount_code or '').strip().lower()

        def promo_applies_to_line(promo: Promotion, line: _Line) -> bool:
            applies_to = str(getattr(promo, 'applies_to', '') or '').strip()
            if applies_to == 'all_products':
                return True
            if applies_to == 'category':
                promo_category = str(getattr(promo, 'category', '') or '').strip().lower()
                return bool(promo_category and promo_category in line.category.lower())
            if applies_to == 'specific_products':
                return line.product_id and promo.products.filter(id=line.product_id).exists()
            return False

        def minimums_ok(promo: Promotion, eligible_lines: list[_Line], current_subtotal: Decimal) -> bool:
            min_subtotal = _d(getattr(promo, 'min_subtotal', 0))
            min_qty = int(getattr(promo, 'min_qty', 0) or 0)
            if min_subtotal > 0 and current_subtotal < min_subtotal:
                return False
            if min_qty > 0 and sum(line.qty for line in eligible_lines) < min_qty:
                return False
            return True

        def calc_discount_amount(promo: Promotion, base_amount: Decimal, eligible_lines: list[_Line]) -> Decimal:
            discount_type = str(getattr(promo, 'discount_type', '') or '').strip()
            discount_value = _d(getattr(promo, 'discount_value', 0))
            if base_amount <= 0:
                return Decimal('0')
            if discount_type == 'percentage':
                return min(base_amount, (base_amount * discount_value / Decimal('100')).quantize(Decimal('0.01')))
            if discount_type == 'fixed_amount':
                return min(base_amount, discount_value)
            if discount_type == 'bundle':
                buy_x = int(getattr(promo, 'buy_x_qty', 0) or 0)
                get_y = int(getattr(promo, 'get_y_qty', 0) or 0)
                total_qty = sum(line.qty for line in eligible_lines)
                if buy_x > 0 and get_y > 0 and total_qty >= buy_x:
                    bundle_count = total_qty // buy_x
                    free_units = bundle_count * get_y
                    discount = Decimal('0')
                    for line in sorted(eligible_lines, key=lambda item: item.unit_price):
                        if free_units <= 0:
                            break
                        units = min(free_units, line.qty)
                        discount += line.unit_price * units
                        free_units -= units
                    return min(base_amount, discount)
                return min(base_amount, discount_value)
            return Decimal('0')

        for promo in promos_sorted:
            if has_non_combinable:
                break
            if not bool(getattr(promo, 'combinable', True)):
                has_non_combinable = True

            trigger_type = str(getattr(promo, 'trigger_type', 'automatic') or 'automatic').strip()
            if trigger_type == 'code':
                promo_code = str(getattr(promo, 'code', '') or '').strip().lower()
                if not promo_code or promo_code != normalized_code:
                    continue

            scope = str(getattr(promo, 'scope', 'product') or 'product').strip()
            if scope == 'product':
                eligible_lines = [line for line in parsed_lines if promo_applies_to_line(promo, line)]
                eligible_subtotal = sum((line.subtotal - line.discount for line in eligible_lines), Decimal('0'))
                if not eligible_lines or eligible_subtotal <= 0:
                    continue
                if not minimums_ok(promo, eligible_lines, eligible_subtotal):
                    continue
                promo_discount = calc_discount_amount(promo, eligible_subtotal, eligible_lines)
                if promo_discount <= 0:
                    continue
                for line in eligible_lines:
                    line_remaining = max(line.subtotal - line.discount, Decimal('0'))
                    share = (line_remaining / eligible_subtotal) if eligible_subtotal > 0 else Decimal('0')
                    line_discount = (promo_discount * share).quantize(Decimal('0.01'))
                    line.discount += min(line_remaining, line_discount)
                product_discount_total += promo_discount
                applied_promotions.append(
                    {
                        'id': str(promo.id),
                        'title': promo.title,
                        'scope': scope,
                        'discount_type': promo.discount_type,
                        'amount_applied': float(promo_discount),
                    }
                )
                continue

            if scope == 'order':
                current_total = max(subtotal - product_discount_total - order_discount_total, Decimal('0'))
                if current_total <= 0:
                    continue
                if not minimums_ok(promo, parsed_lines, current_total):
                    continue
                promo_discount = calc_discount_amount(promo, current_total, parsed_lines)
                if promo_discount <= 0:
                    continue
                order_discount_total += promo_discount
                applied_promotions.append(
                    {
                        'id': str(promo.id),
                        'title': promo.title,
                        'scope': scope,
                        'discount_type': promo.discount_type,
                        'amount_applied': float(promo_discount),
                    }
                )
                continue

            if scope == 'shipping':
                shipping_base = _d(shipping_amount)
                if shipping_base <= 0:
                    continue
                if not minimums_ok(promo, parsed_lines, subtotal):
                    continue
                if str(getattr(promo, 'discount_type', '') or '') == 'free_shipping':
                    promo_discount = shipping_base
                else:
                    promo_discount = calc_discount_amount(promo, shipping_base, parsed_lines)
                if promo_discount <= 0:
                    continue
                shipping_discount_total += promo_discount
                applied_promotions.append(
                    {
                        'id': str(promo.id),
                        'title': promo.title,
                        'scope': scope,
                        'discount_type': promo.discount_type,
                        'amount_applied': float(promo_discount),
                    }
                )

        line_items = []
        for line in parsed_lines:
            line_items.append(
                {
                    'product_id': line.product_id,
                    'qty': line.qty,
                    'unit_price': float(line.unit_price),
                    'subtotal': float(line.subtotal),
                    'discount': float(line.discount),
                    'total': float(max(line.subtotal - line.discount, Decimal('0'))),
                    'category': line.category,
                }
            )

        discount_total = product_discount_total + order_discount_total + shipping_discount_total
        total = max(subtotal - product_discount_total - order_discount_total, Decimal('0'))
        total_with_shipping = max(total + _d(shipping_amount) - shipping_discount_total, Decimal('0'))

        return {
            'subtotal': float(subtotal),
            'product_discount_total': float(product_discount_total),
            'order_discount_total': float(order_discount_total),
            'shipping_discount_total': float(shipping_discount_total),
            'discount_total': float(discount_total),
            'total': float(total),
            'total_with_shipping': float(total_with_shipping),
            'applied_promotions': applied_promotions,
            'line_items': line_items,
            'free_shipping': bool(shipping_discount_total > 0 and _d(shipping_amount) > 0),
        }
