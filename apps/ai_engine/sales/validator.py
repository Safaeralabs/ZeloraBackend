"""
Response Validator â€” Validates LLM responses don't hallucinate products/prices.
"""
import logging
import re

logger = logging.getLogger(__name__)


class ResponseValidator:
    """
    Post-generation response validation to prevent hallucinations.
    Checks mentions of products, prices, and injection attempts.
    """

    @staticmethod
    def validate(reply: str, context: dict) -> str:
        """
        Validate response against context.

        Args:
            reply: Generated response text
            context: Context dict with available products, KB, etc.

        Returns:
            Validated (possibly sanitized) reply string
        """
        if not reply:
            return reply

        try:
            # Injection check runs regardless of context â€” it's a text-only guard
            if ResponseValidator._has_injection_signals(reply):
                logger.warning('Detected injection signals in response, filtering')
                reply = ResponseValidator._remove_injection_lines(reply)

            if not context:
                return reply

            # Brand guard: deterministically strip phrases the brand forbids
            brand_guard = context.get('brand_guard')
            if isinstance(brand_guard, dict):
                reply = ResponseValidator._enforce_brand_guard(reply, brand_guard, context)
                if not reply:
                    return ResponseValidator._fallback_reply(context)

            # Check for product hallucinations
            if context.get('recommended_products') or context.get('catalog_titles'):
                product_names = [p['title'].lower() for p in (context.get('recommended_products') or [])]
                if ResponseValidator._has_suspicious_product_mention(
                    reply,
                    product_names,
                    catalog_titles=context.get('catalog_titles'),
                ):
                    logger.warning('Detected possible product hallucination in response')
                    return ResponseValidator._fallback_reply(context)

            # Check for price hallucinations. Past-order totals (surfaced when
            # the customer references a prior order) count as known-good too,
            # so quoting them back is never flagged just because they don't
            # match the CURRENT cart's prices.
            prices = [float(t) for t in (context.get('customer_history_totals') or []) if t]
            for p in (context.get('recommended_products') or []):
                if p.get('price_min'):
                    prices.append(float(p['price_min']))
                if p.get('price_max'):
                    prices.append(float(p['price_max']))

            if prices and ResponseValidator._has_suspicious_price_mention(reply, prices):
                logger.warning('Detected possible price hallucination in response')
                return ResponseValidator._fallback_reply(context)

            return reply

        except Exception as e:
            logger.error(f'Response validation error: {e}')
            return reply

    @staticmethod
    def _enforce_brand_guard(reply: str, brand_guard: dict, context: dict) -> str:
        """
        Remove sentences containing phrases the brand forbids
        (brand.avoid_phrases + commerce_rules.forbidden_claims/promises).
        Returns '' when nothing usable remains so the caller can fall back.
        """
        banned = [
            ResponseValidator._normalize_text(str(phrase))
            for phrase in (
                (brand_guard.get('avoid_phrases') or [])
                + (brand_guard.get('forbidden_claims') or [])
            )
        ]
        banned = [phrase for phrase in banned if phrase]
        if not banned:
            return reply

        kept_lines = []
        removed_any = False
        for line in reply.split('\n'):
            sentences = re.split(r'(?<=[.!?])\s+', line)
            kept_sentences = []
            for sentence in sentences:
                normalized = ResponseValidator._normalize_text(sentence)
                if normalized and any(phrase in normalized for phrase in banned):
                    removed_any = True
                    continue
                kept_sentences.append(sentence)
            kept_lines.append(' '.join(kept_sentences).strip())

        if removed_any:
            logger.warning('Brand guard removed forbidden phrasing from response')
        cleaned = '\n'.join(line for line in kept_lines if line).strip()
        return cleaned

    #: Bolded phrases that are commerce formatting, not product titles.
    _BENIGN_BOLD_PREFIXES = (
        'total', 'subtotal', 'precio', 'envio', 'descuento', 'promocion',
        'oferta', 'gratis', 'metodo de pago', 'nota', 'importante', 'stock',
        'disponible', 'pedido', 'resumen',
    )

    @staticmethod
    def _has_suspicious_product_mention(reply: str, product_names: list, catalog_titles: list | None = None) -> bool:
        """
        Check if the reply presents (in bold, the product-title convention) a
        product that does not exist in the org's catalog.

        The allowed set is the FULL org catalog when available — mentioning a
        real product outside the current recommendation context is never
        hallucination — falling back to the recommended products otherwise.
        """
        allowed = [
            ResponseValidator._normalize_text(str(name))
            for name in (list(catalog_titles or []) + list(product_names or []))
        ]
        allowed = [name for name in allowed if name]
        if not allowed:
            return False

        # Only the bolded-title convention is treated as a product claim. The old
        # hardcoded noun list (top|legging|camiseta...) caused false positives for
        # any store whose products use those words in normal speech.
        for candidate in re.findall(r'\*\*([^*]+)\*\*', reply):
            if '$' in candidate:
                continue  # bolded totals/prices, not a product title
            normalized = ResponseValidator._normalize_text(candidate)
            if not normalized or len(normalized) < 4 or normalized.isdigit():
                continue
            if any(normalized.startswith(prefix) for prefix in ResponseValidator._BENIGN_BOLD_PREFIXES):
                continue
            if not any(normalized in name or name in normalized for name in allowed):
                return True

        return False

    @staticmethod
    def _has_suspicious_price_mention(reply: str, known_prices: list) -> bool:
        """
        Check if reply mentions prices not in the known product prices.

        Args:
            reply: Response text
            known_prices: List of valid prices from products

        Returns:
            True if suspicious prices detected
        """
        # Extract prices from reply
        price_pattern = r'\$[\d,]+(?:\.\d{2})?'
        prices_in_reply = []

        for match in re.finditer(price_pattern, reply):
            try:
                price = float(match.group(0).replace('$', '').replace(',', ''))
                prices_in_reply.append(price)
            except ValueError:
                pass

        # If reply mentions prices but they don't match our catalog, flag it
        if prices_in_reply and known_prices:
            # Check if any price in reply is way off (> 50% different from closest known price)
            for mentioned_price in prices_in_reply:
                if mentioned_price <= 0:
                    continue
                closest_known = min(known_prices, key=lambda x: abs(x - mentioned_price))
                if closest_known <= 0:
                    continue
                price_diff_percent = abs(mentioned_price - closest_known) / closest_known * 100

                # Very strict: if price is >50% off, it's likely hallucinated —
                # unless it's a subtotal (unit price x quantity), which routinely
                # lands >50% away from the unit price itself (e.g. 3 cuadernos
                # x $50,000 = $150,000, 200% "off" the $50,000 unit price).
                if price_diff_percent > 50 and not ResponseValidator._is_plausible_subtotal(mentioned_price, known_prices):
                    return True

        return False

    @staticmethod
    def _is_plausible_subtotal(mentioned_price: float, known_prices: list, max_quantity: int = 30) -> bool:
        """
        True when `mentioned_price` is an (almost) exact multiple of a known
        unit price for a plausible quantity (2-30 units). Real subtotals land
        within a tight tolerance; hallucinated prices essentially never do.
        """
        for unit_price in known_prices:
            if unit_price <= 0:
                continue
            quantity = round(mentioned_price / unit_price)
            if quantity < 2 or quantity > max_quantity:
                continue
            expected = unit_price * quantity
            if abs(mentioned_price - expected) / expected * 100 <= 1:
                return True
        return False

    @staticmethod
    def _normalize_text(value: str) -> str:
        lowered = value.lower().strip()
        lowered = re.sub(r'[^a-z0-9Ã¡Ã©Ã­Ã³ÃºÃ±\s-]+', ' ', lowered)
        return re.sub(r'\s+', ' ', lowered).strip()

    #: Injection echoes require instruction-context, not lone common words.
    #: Bare 'cambia'/'olvida'/'ignora' nuked normal sales Spanish like
    #: "si cambias de opinión" and replaced real replies with generic fallbacks.
    _INJECTION_PATTERNS = [
        re.compile(pattern, re.IGNORECASE)
        for pattern in (
            r'\bignor\w*\b[^.!?\n]{0,50}\b(instrucci[oó]n|regla|prompt|sistema|indicaci[oó]n)',
            r'\bolvid\w*\b[^.!?\n]{0,50}\b(instrucci[oó]n|regla|prompt|todo lo anterior|lo que te dije)',
            r'\bignore\b[^.!?\n]{0,50}\b(instructions?|rules?|prompts?)\b',
            r'\bdisregard\b[^.!?\n]{0,50}\b(instructions?|rules?|prompts?)\b',
            r'\bmy (instructions|rules)\b',
            r'\bsystem prompt\b',
            r'\bsoy ahora\b',
            r'\bpretendo ser\b',
            r'\bact[uú]a como (si fueras|otro|una ia|un modelo|un asistente diferente)\b',
        )
    ]

    @staticmethod
    def _has_injection_signals(reply: str) -> bool:
        """
        Check for signs of prompt injection being echoed in the response.
        """
        return any(pattern.search(reply) for pattern in ResponseValidator._INJECTION_PATTERNS)

    @staticmethod
    def _remove_injection_lines(reply: str) -> str:
        """
        Remove only the lines that match an injection pattern, keeping the rest.
        """
        cleaned = [
            line for line in reply.split('\n')
            if not any(pattern.search(line) for pattern in ResponseValidator._INJECTION_PATTERNS)
        ]
        return '\n'.join(cleaned).strip()

    @staticmethod
    def _fallback_reply(context: dict | None = None) -> str:
        """
        Return safe fallback when hallucination detected.

        Returns:
            Safe generic reply
        """
        products = []
        if isinstance(context, dict):
            products = context.get('recommended_products') or []
        if products:
            return 'Te ayudo con gusto. Ahora mismo tengo opciones disponibles para ti. ¿Cual te interesa?'
        return 'Te ayudo con gusto. ¿Buscas productos, precio o completar una compra?'

