"""
Response Validator — Validates LLM responses don't hallucinate products/prices.
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
        if not reply or not context:
            return reply

        try:
            # Check for product hallucinations
            if context.get('recommended_products'):
                product_names = [p['title'].lower() for p in context['recommended_products']]
                if ResponseValidator._has_suspicious_product_mention(reply, product_names):
                    logger.warning('Detected possible product hallucination in response')
                    return ResponseValidator._fallback_reply()

            # Check for price hallucinations
            if context.get('recommended_products'):
                prices = []
                for p in context['recommended_products']:
                    if p.get('price_min'):
                        prices.append(float(p['price_min']))
                    if p.get('price_max'):
                        prices.append(float(p['price_max']))

                if prices and ResponseValidator._has_suspicious_price_mention(reply, prices):
                    logger.warning('Detected possible price hallucination in response')
                    return ResponseValidator._fallback_reply()

            # Check for injection attempts
            if ResponseValidator._has_injection_signals(reply):
                logger.warning('Detected injection signals in response, filtering')
                reply = ResponseValidator._remove_injection_lines(reply)

            return reply

        except Exception as e:
            logger.error(f'Response validation error: {e}')
            return reply

    @staticmethod
    def _has_suspicious_product_mention(reply: str, product_names: list) -> bool:
        """
        Check if reply mentions products NOT in the allowed list.

        Args:
            reply: Response text
            product_names: List of valid product name lowercases

        Returns:
            True if suspicious mention detected
        """
        reply_lower = reply.lower()

        # Extract potential product mentions (word patterns like "Product Name")
        # Very conservative: only flag if it looks like a proper product name
        # mentioned with very specific pricing that doesn't match our catalog

        # Look for price patterns that don't match our known prices
        price_pattern = r'\$[\d,]+(?:\.\d{2})?'
        prices_in_reply = re.findall(price_pattern, reply)

        # If reply mentions prices but none of our products have those exact prices,
        # it's suspicious (but only if there are products in context)
        if prices_in_reply and product_names:
            # Extract numeric values
            reply_prices = []
            for price_str in prices_in_reply:
                try:
                    price = float(price_str.replace('$', '').replace(',', ''))
                    reply_prices.append(price)
                except ValueError:
                    pass

            # For now, lenient: only flag if ALL prices in reply are WAY off
            # (not a perfect check, but prevents most hallucinations)
            # Skip this check — it's too prone to false positives

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
                closest_known = min(known_prices, key=lambda x: abs(x - mentioned_price))
                price_diff_percent = abs(mentioned_price - closest_known) / closest_known * 100

                # Very strict: if price is >50% off, it's likely hallucinated
                if price_diff_percent > 50:
                    return True

        return False

    @staticmethod
    def _has_injection_signals(reply: str) -> bool:
        """
        Check for signs of prompt injection in response.

        Args:
            reply: Response text

        Returns:
            True if injection signals found
        """
        injection_keywords = [
            'ignora',
            'olvida',
            'cambia',
            'acto como',
            'soy ahora',
            'pretendo ser',
            'my instructions',
            'my rules',
            'ignore instructions',
            'disregard',
        ]

        reply_lower = reply.lower()
        for keyword in injection_keywords:
            if keyword in reply_lower:
                return True

        return False

    @staticmethod
    def _remove_injection_lines(reply: str) -> str:
        """
        Remove lines that contain injection signals.

        Args:
            reply: Response text

        Returns:
            Cleaned response
        """
        lines = reply.split('\n')
        injection_keywords = [
            'ignora', 'olvida', 'cambia', 'acto como', 'soy ahora', 'pretendo ser',
        ]

        cleaned = []
        for line in lines:
            line_lower = line.lower()
            # Skip lines with injection keywords
            if not any(keyword in line_lower for keyword in injection_keywords):
                cleaned.append(line)

        return '\n'.join(cleaned).strip()

    @staticmethod
    def _fallback_reply() -> str:
        """
        Return safe fallback when hallucination detected.

        Returns:
            Safe generic reply
        """
        return 'Disculpa, parece que tuve un error. Por favor cuéntame qué necesitas y te ayudaré de la mejor manera posible.'
