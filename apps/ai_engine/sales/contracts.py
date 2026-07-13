"""
Post-generation response contracts for stage-safe outputs.
"""
from __future__ import annotations
import re


class ResponseContractEnforcer:
    @staticmethod
    def enforce(
        *,
        reply: str,
        session_stage: str,
        action: dict,
        context: dict,
        user_message: str,
    ) -> str:
        text = (reply or '').strip()
        if not text:
            return ResponseContractEnforcer._generic_help(context)

        if ResponseContractEnforcer._contains_internal_error_text(text):
            ResponseContractEnforcer._bump_metric(context, 'internal_error_text_prevented')
            text = ResponseContractEnforcer._generic_help(context)

        text = ResponseContractEnforcer._enforce_similar_products_contract(
            reply=text,
            context=context,
            user_message=user_message,
        )
        text = ResponseContractEnforcer._enforce_variant_availability_contract(
            reply=text,
            context=context,
            user_message=user_message,
        )
        text = ResponseContractEnforcer._enforce_checkout_contract(
            reply=text,
            session_stage=session_stage,
            action=action,
            context=context,
            user_message=user_message,
        )
        text = ResponseContractEnforcer._enforce_post_order_payment_contract(
            reply=text,
            context=context,
            user_message=user_message,
        )
        return text

    @staticmethod
    def _enforce_checkout_contract(
        *,
        reply: str,
        session_stage: str,
        action: dict,
        context: dict,
        user_message: str,
    ) -> str:
        in_checkout = (session_stage == 'checkout') or bool((action or {}).get('checkout_step'))
        if not in_checkout:
            return reply

        checkout_data = dict(context.get('checkout_data') or {})
        compact_form = dict(checkout_data.get('compact_checkout_form') or {})
        has_order = bool(str(checkout_data.get('order_id') or '').strip())
        selected_payment = str(compact_form.get('payment_method') or '').strip().lower()
        user_lower = str(user_message or '').lower()
        asked_transfer = 'transferencia' in user_lower
        wants_transfer = selected_payment == 'transferencia_bancaria' or asked_transfer

        payment_methods = [
            item for item in ((context.get('payment_profile') or {}).get('methods') or [])
            if isinstance(item, dict)
        ]
        transfer_method = next(
            (
                item for item in payment_methods
                if str(item.get('id') or '').strip() == 'transferencia_bancaria'
            ),
            {},
        )
        transfer_instructions = str(transfer_method.get('instructions') or '').strip()

        if (
            not wants_transfer
            and not selected_payment
            and payment_methods
            and not ResponseContractEnforcer._asks_for_payment_method(reply)
        ):
            ResponseContractEnforcer._bump_metric(context, 'payment_method_prompt_enforced')
            labels = [
                str(item.get('label') or '').strip()
                for item in payment_methods
                if str(item.get('label') or '').strip()
            ]
            options_text = ', '.join(labels) if labels else 'el metodo de pago disponible'
            return f'Para continuar con tu pedido, elige metodo de pago: {options_text}.'

        if wants_transfer and not has_order:
            lowered_reply = (reply or '').lower()
            if any(
                token in lowered_reply
                for token in ('me faltan', 'faltan', 'formulario', 'confirmas que cree el pedido')
            ):
                return reply
            ResponseContractEnforcer._bump_metric(context, 'preorder_transfer_blocked')
            return (
                'Perfecto, dejamos transferencia bancaria seleccionada. '
                'Antes de pagar, debo crear y confirmar tu pedido con tus datos de checkout.'
            )

        if wants_transfer and transfer_instructions:
            if not ResponseContractEnforcer._contains_transfer_details(reply):
                ResponseContractEnforcer._bump_metric(context, 'transfer_details_enforced')
                return (
                    'Perfecto. Puedes pagar por transferencia bancaria. '
                    f'Datos: {transfer_instructions}. '
                    'Cuando realices el pago, enviame una captura de pantalla del comprobante '
                    'para validar tu pedido.'
                )

        if wants_transfer and not transfer_instructions:
            ResponseContractEnforcer._bump_metric(context, 'transfer_details_missing_escalated')
            return (
                'Perfecto, tomo transferencia bancaria. '
                'Ahora mismo no tengo los datos de cuenta configurados; te conecto con soporte para compartirlos.'
            )

        return reply

    @staticmethod
    def _enforce_similar_products_contract(*, reply: str, context: dict, user_message: str) -> str:
        if not ResponseContractEnforcer._asked_for_similar_products(user_message):
            return reply

        products = [item for item in (context.get('recommended_products') or []) if isinstance(item, dict)]
        if not products:
            ResponseContractEnforcer._bump_metric(context, 'similar_contract_enforced')
            return 'Ahora mismo no tengo productos similares disponibles.'

        if len(products) == 1:
            title = str(products[0].get('title') or 'este producto').strip()
            normalized = (reply or '').lower()
            if 'solo' in normalized or 'actualmente' in normalized or 'por ahora' in normalized:
                return reply
            ResponseContractEnforcer._bump_metric(context, 'similar_contract_enforced')
            return f'Por ahora solo tengo {title} disponible. Si quieres, te ayudo a comprarlo.'

        top_products = products[:3]
        mentioned = 0
        normalized_reply = (reply or '').lower()
        for product in top_products:
            title = str(product.get('title') or '').strip()
            if title and title.lower() in normalized_reply:
                mentioned += 1

        if mentioned >= 2:
            return reply

        lines = ['Te comparto opciones similares que tengo disponibles:']
        for product in top_products[:2]:
            title = str(product.get('title') or 'Producto').strip()
            price = product.get('price_min')
            if price:
                lines.append(f'- {title} (${int(float(price)):,})')
            else:
                lines.append(f'- {title}')
        lines.append('¿Cual prefieres?')
        ResponseContractEnforcer._bump_metric(context, 'similar_contract_enforced')
        return ' '.join(lines)

    @staticmethod
    def _enforce_variant_availability_contract(*, reply: str, context: dict, user_message: str) -> str:
        if not ResponseContractEnforcer._asked_for_variant_availability(user_message):
            return reply

        variant = context.get('variant_info') or {}
        if not isinstance(variant, dict):
            if ResponseContractEnforcer._sounds_uncertain_variant_reply(reply):
                ResponseContractEnforcer._bump_metric(context, 'variant_info_missing_escalation_prompted')
                return (
                    'No tengo confirmacion de talla en este momento. '
                    'Si quieres, te conecto con un asesor humano para validarla ahora mismo.'
                )
            return reply

        available = [
            str(item).strip()
            for item in (variant.get('labels_available') or [])
            if str(item).strip()
        ]
        unavailable = [
            str(item).strip()
            for item in (variant.get('labels_unavailable') or [])
            if str(item).strip()
        ]
        if not available and not unavailable:
            if ResponseContractEnforcer._sounds_uncertain_variant_reply(reply):
                ResponseContractEnforcer._bump_metric(context, 'variant_info_missing_escalation_prompted')
                return (
                    'No tengo confirmacion de talla en este momento. '
                    'Si quieres, te conecto con un asesor humano para validarla ahora mismo.'
                )
            return reply

        lowered = (reply or '').lower()
        def _mentions_label(text: str, label: str) -> bool:
            candidate = str(label or '').strip().lower()
            if not candidate:
                return False
            if len(candidate) <= 2:
                return bool(re.search(rf'\b{re.escape(candidate)}\b', text))
            return candidate in text

        if any(_mentions_label(lowered, label) for label in available[:6]):
            return reply

        product_title = str(variant.get('product_title') or 'este producto').strip()
        ResponseContractEnforcer._bump_metric(context, 'variant_contract_enforced')
        if available:
            available_text = ', '.join(available[:6])
            if unavailable:
                unavailable_text = ', '.join(unavailable[:6])
                return (
                    f'Si, para {product_title} tengo disponibles: {available_text}. '
                    f'Ahora mismo estan agotadas: {unavailable_text}.'
                )
            return f'Si, para {product_title} tengo disponibles: {available_text}.'

        unavailable_text = ', '.join(unavailable[:6])
        return f'Ahora mismo {product_title} no tiene tallas disponibles. Agotadas: {unavailable_text}.'

    @staticmethod
    def _sounds_uncertain_variant_reply(reply: str) -> bool:
        lowered = str(reply or '').lower()
        return any(
            token in lowered
            for token in (
                'no tengo informacion',
                'no tengo información',
                'no tengo confirmacion',
                'no tengo confirmación',
                'lamento la confusion',
                'lamento la confusión',
                'no cuento con',
            )
        )

    @staticmethod
    def _enforce_post_order_payment_contract(*, reply: str, context: dict, user_message: str) -> str:
        checkout_data = context.get('checkout_data')
        if not isinstance(checkout_data, dict):
            return reply
        if not str(checkout_data.get('order_id') or '').strip():
            return reply
        if not ResponseContractEnforcer._asked_for_payment_details(user_message):
            return reply

        selected_method = str(checkout_data.get('payment_method') or '').strip().lower()
        selected_label = str(checkout_data.get('payment_method_label') or '').strip()
        wants_transfer = (
            selected_method == 'transferencia_bancaria'
            or 'transferencia' in str(user_message or '').lower()
        )
        if not wants_transfer:
            return reply

        instructions = str(checkout_data.get('payment_instructions') or '').strip()
        if not instructions:
            methods = [
                item for item in ((context.get('payment_profile') or {}).get('methods') or [])
                if isinstance(item, dict)
            ]
            transfer = next(
                (
                    item for item in methods
                    if str(item.get('id') or '').strip() == 'transferencia_bancaria'
                ),
                {},
            )
            instructions = str(transfer.get('instructions') or '').strip()

        if instructions and not ResponseContractEnforcer._contains_transfer_details(reply):
            ResponseContractEnforcer._bump_metric(context, 'post_order_transfer_details_enforced')
            return (
                f'Claro. Tu pedido esta con {selected_label or "transferencia bancaria"}. '
                f'Datos para pagar: {instructions}. '
                'Cuando lo hagas, enviame una captura de pantalla del comprobante y validamos el pago.'
            )

        if not instructions:
            ResponseContractEnforcer._bump_metric(context, 'post_order_transfer_details_missing_escalated')
            return (
                'Tu pedido esta por transferencia bancaria, pero no tengo la cuenta configurada en este momento. '
                'Te conecto con soporte para compartirte los datos exactos ahora mismo.'
            )

        return reply

    @staticmethod
    def _contains_internal_error_text(reply: str) -> bool:
        lowered = (reply or '').lower()
        return any(
            token in lowered
            for token in (
                'tuve un error',
                'parece que tuve un error',
                'error procesando',
            )
        )

    @staticmethod
    def _contains_transfer_details(reply: str) -> bool:
        lowered = (reply or '').lower()
        required_tokens = ('transferencia', 'cuenta', 'titular')
        return all(token in lowered for token in required_tokens)

    @staticmethod
    def _asks_for_payment_method(reply: str) -> bool:
        lowered = (reply or '').lower()
        return ('metodo de pago' in lowered) or ('método de pago' in lowered) or ('como prefieres pagar' in lowered)

    @staticmethod
    def _generic_help(context: dict) -> str:
        if (context.get('recommended_products') or []):
            return 'Te ayudo con gusto. Tengo opciones disponibles para ti. ¿Cual te interesa?'
        return 'Te ayudo con gusto. ¿Buscas productos, precio o completar una compra?'

    @staticmethod
    def _asked_for_similar_products(user_message: str) -> bool:
        lowered = str(user_message or '').lower()
        keywords = (
            'similar',
            'similares',
            'parecido',
            'parecidos',
            'que otros',
            'qué otros',
            'otro producto',
            'otras opciones',
            'otro similar',
        )
        return any(keyword in lowered for keyword in keywords)

    @staticmethod
    def _asked_for_variant_availability(user_message: str) -> bool:
        lowered = str(user_message or '').lower()
        keywords = (
            'talla',
            'tallas',
            'size',
            'sizes',
            'color',
            'colores',
            'sku',
            'referencia',
        )
        return any(keyword in lowered for keyword in keywords)

    @staticmethod
    def _asked_for_payment_details(user_message: str) -> bool:
        lowered = str(user_message or '').lower()
        keywords = (
            'como lo pago',
            'cómo lo pago',
            'como pago',
            'cómo pago',
            'que cuenta',
            'qué cuenta',
            'numero de cuenta',
            'número de cuenta',
            'datos bancarios',
            'cuenta bancaria',
            'donde transfiero',
            'dónde transfiero',
            'a que cuenta',
            'a qué cuenta',
            'transferencia',
        )
        return any(keyword in lowered for keyword in keywords)

    @staticmethod
    def _bump_metric(context: dict, key: str) -> None:
        if not isinstance(context, dict):
            return
        checkout_data = context.get('checkout_data')
        if not isinstance(checkout_data, dict):
            checkout_data = {}
            context['checkout_data'] = checkout_data
        metrics = checkout_data.get('contract_metrics')
        if not isinstance(metrics, dict):
            metrics = {}
            checkout_data['contract_metrics'] = metrics
        metrics[key] = int(metrics.get(key, 0) or 0) + 1
