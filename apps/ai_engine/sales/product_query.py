"""
Product query interpretation for sales search.
"""
import json
import logging
import re

from django.conf import settings
import openai

from .llm_router import LLMRouter

logger = logging.getLogger(__name__)


class ProductQueryInterpreter:
    BROWSE_PATTERNS = (
        'que productos',
        'qué productos',
        'que tienes',
        'qué tienes',
        'que manejas',
        'qué manejas',
        'que hay',
        'qué hay',
        'que opciones',
        'qué opciones',
        'mostrar productos',
        'muéstrame productos',
        'ver productos',
        'otros productos',
        'otras opciones',
        'productos similares',
        'catalogo',
        'catálogo',
        'disponibles',
    )

    @staticmethod
    def interpret(query: str, session=None) -> dict:
        normalized = ProductQueryInterpreter._normalize(query)
        heuristic = ProductQueryInterpreter._heuristic_interpret(normalized)

        if heuristic.get('is_catalog_browse'):
            return heuristic

        if not settings.OPENAI_API_KEY or not settings.ENABLE_REAL_AI:
            return heuristic

        try:
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            model = LLMRouter.model_for_task('entity_extraction')
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            'Extrae la intención de búsqueda de catálogo. '
                            'Devuelve JSON válido con: '
                            'is_catalog_browse, product_name, category, color, brand, '
                            'attributes, search_terms, allow_alternatives, confidence.'
                        ),
                    },
                    {
                        'role': 'user',
                        'content': (
                            f'Consulta del cliente: "{query}"\n'
                            'Si la persona está explorando catálogo general, marca is_catalog_browse=true. '
                            'Si no recuerdas el nombre exacto, no inventes product_name.'
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=200,
            )
            payload = json.loads(response.choices[0].message.content.strip())
            interpreted = {
                'is_catalog_browse': bool(payload.get('is_catalog_browse')),
                'product_name': ProductQueryInterpreter._as_text(payload.get('product_name')),
                'category': ProductQueryInterpreter._as_text(payload.get('category')),
                'color': ProductQueryInterpreter._as_text(payload.get('color')),
                'brand': ProductQueryInterpreter._as_text(payload.get('brand')),
                'attributes': ProductQueryInterpreter._clean_terms(payload.get('attributes') or []),
                'search_terms': ProductQueryInterpreter._clean_terms(payload.get('search_terms') or []),
                'allow_alternatives': bool(payload.get('allow_alternatives', True)),
                'confidence': float(payload.get('confidence') or 0.0),
            }
            if interpreted['is_catalog_browse']:
                return interpreted

            # Merge heuristic terms to keep recall high.
            merged_terms = interpreted['search_terms'] + heuristic.get('search_terms', [])
            interpreted['search_terms'] = ProductQueryInterpreter._dedupe(merged_terms)
            if not interpreted['product_name']:
                interpreted['product_name'] = heuristic.get('product_name', '')
            if not interpreted['category']:
                interpreted['category'] = heuristic.get('category', '')
            if not interpreted['color']:
                interpreted['color'] = heuristic.get('color', '')
            if not interpreted['attributes']:
                interpreted['attributes'] = heuristic.get('attributes', [])
            return interpreted
        except Exception as exc:
            logger.warning(f'Product query interpretation failed: {exc}')
            return heuristic

    @staticmethod
    def _heuristic_interpret(normalized_query: str) -> dict:
        if not normalized_query:
            return {
                'is_catalog_browse': True,
                'product_name': '',
                'category': '',
                'color': '',
                'brand': '',
                'attributes': [],
                'search_terms': [],
                'allow_alternatives': True,
                'confidence': 0.2,
            }

        is_catalog_browse = any(pattern in normalized_query for pattern in ProductQueryInterpreter.BROWSE_PATTERNS)

        colors = {
            'negro', 'negra', 'blanco', 'blanca', 'azul', 'rojo', 'roja',
            'verde', 'gris', 'arena', 'beige', 'rosado', 'rosa',
        }
        categories = {
            'camiseta', 'top', 'legging', 'leggings', 'pantalon', 'pantalón',
            'sudadera', 'chaqueta', 'guantes', 'oximetro', 'oxímetro',
        }
        filler = {
            'hola', 'que', 'qué', 'tienes', 'tienen', 'hay', 'ahora', 'disponible',
            'disponibles', 'muéstrame', 'mostrar', 'productos', 'producto',
            'quisiera', 'quiero', 'saber', 'precio', 'vale', 'cuesta', 'me',
            'interesa', 'tienen?', 'disp', 'ahí', 'ahi', 'ahora?',
            # Buy verbs and generic words carry no product signal.
            'comprar', 'comprarlo', 'comprarla', 'compra', 'gustaria', 'gustaría',
            'llevar', 'llevarlo', 'llevarla', 'otros', 'otras', 'otro', 'otra',
            'mas', 'más', 'algo', 'ver', 'dame', 'como', 'cómo',
        }

        words = [w for w in normalized_query.split() if len(w) > 2]
        search_terms = [w for w in words if w not in filler]
        if not search_terms:
            # Nothing meaningful to search: treat as catalog exploration so the
            # customer sees products instead of an empty "no match".
            is_catalog_browse = True
        color = next((w for w in search_terms if w in colors), '')
        category = next((w for w in search_terms if w in categories), '')

        product_name = ''
        if not is_catalog_browse and len(search_terms) >= 2:
            product_name = ' '.join(search_terms[:6])

        return {
            'is_catalog_browse': is_catalog_browse,
            'product_name': product_name,
            'category': category,
            'color': color,
            'brand': '',
            'attributes': [w for w in search_terms if w not in {color, category}],
            'search_terms': search_terms[:6],
            'allow_alternatives': True,
            'confidence': 0.55 if product_name else 0.35,
        }

    @staticmethod
    def _as_text(value) -> str:
        """
        The extraction LLM occasionally returns a list instead of a string for
        a field (e.g. category=["pantalon", "camisa"] on a compound query like
        "pantalon o camisa?") — coerce defensively instead of crashing.
        """
        if isinstance(value, list):
            return ' '.join(str(item).strip() for item in value if str(item).strip())
        return str(value or '').strip()

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r'\s+', ' ', (value or '').strip().lower())

    @staticmethod
    def _clean_terms(values) -> list[str]:
        if not isinstance(values, list):
            return []
        return ProductQueryInterpreter._dedupe(
            [str(value).strip().lower() for value in values if str(value).strip()]
        )

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen = set()
        result = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result
