"""
Product Photo Analyzer — turns a product photo into draft catalog fields.

Two-call pipeline, both on the same LLMRouter tiers the Sales Agent already
uses (see apps.ai_engine.sales.llm_router):
  1. Extraction (nano, escalates to premium on low confidence): is this a
     sellable product photo at all, what category/attributes are visible.
  2. Copy (mini): turns the raw attributes into a title + description in the
     org's own voice, reusing the same business-context lines the Sales
     Agent's system prompt uses.

Nothing here ever creates a Product. It only returns a suggestion; the
caller (ProductViewSet.analyze_photo) hands it back to the client for the
human to review and edit before anything is saved.
"""
from __future__ import annotations

import base64
import json
import logging

from django.conf import settings

from apps.ai_engine.sales.llm_router import LLMRouter
from apps.ai_engine.sales.brand import BrandVoice

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_THRESHOLD = 0.55

EXTRACTION_SYSTEM_PROMPT = """Eres un asistente que examina UNA foto de producto tomada por un comerciante \
para ayudarlo a darlo de alta en su catalogo.

Responde EXCLUSIVAMENTE con un JSON con esta forma exacta, sin texto adicional:
{
  "is_product_photo": true|false,
  "rejection_reason": "" | "no_product" | "inappropriate" | "unclear",
  "category": "string corta, ej: Calzado, Ropa, Accesorios, Hogar, Electronica, Belleza, Alimentos, Otro",
  "attributes": ["hasta 5 atributos visibles: color, material, tipo, marca SOLO si es legible con certeza en la foto"],
  "suggested_title": "nombre de producto corto y descriptivo, sin inventar marca si no es visible",
  "confidence": 0.0-1.0
}

Reglas:
- "is_product_photo" es false si la imagen no muestra un producto vendible (persona, paisaje, documento, pantalla, etc.) \
o si el contenido es inapropiado (violencia, contenido sexual, armas, drogas) — en ese caso usa "rejection_reason" \
y deja el resto de campos vacios o en 0.
- Nunca afirmes una marca registrada a menos que el logo o etiqueta sea claramente legible en la foto. Si no estas \
seguro, omite la marca del titulo.
- "confidence" debe reflejar que tan seguro estas de la categoria y el titulo, no de la foto en si.
- No inventes atributos que no puedas ver."""

COPY_SYSTEM_PROMPT = """Escribes una ficha de producto corta para un catalogo conversacional en español. \
Con el contexto del negocio y los atributos detectados en una foto, produce:
{
  "title": "titulo de venta, maximo 60 caracteres, sin inventar datos que no te dieron",
  "description": "1-2 frases que ayuden a vender, tono acorde al negocio, sin inventar caracteristicas no confirmadas"
}
Responde solo el JSON, sin texto adicional. Si el contexto del negocio es escaso, mantente neutral y honesto."""


class ProductPhotoAnalyzer:
    @staticmethod
    def analyze(image_bytes: bytes, organization) -> dict:
        """
        Returns a dict always shaped as:
        {
          'ok': bool,
          'rejection_reason': str | None,
          'category': str,
          'suggested_title': str,
          'description': str,
          'attributes': list[str],
          'confidence': float,
          'model_used': str,
        }
        """
        if not settings.OPENAI_API_KEY or not settings.ENABLE_REAL_AI:
            return ProductPhotoAnalyzer._unavailable()

        try:
            import openai

            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            data_uri = 'data:image/jpeg;base64,' + base64.b64encode(image_bytes).decode('ascii')

            model = LLMRouter.model_for_task('entity_extraction')
            extraction = ProductPhotoAnalyzer._extract(client, data_uri, model)

            if not extraction.get('is_product_photo'):
                return {
                    'ok': False,
                    'rejection_reason': extraction.get('rejection_reason') or 'unclear',
                    'category': '',
                    'suggested_title': '',
                    'description': '',
                    'attributes': [],
                    'confidence': 0.0,
                    'model_used': model,
                }

            confidence = float(extraction.get('confidence') or 0)
            if confidence < LOW_CONFIDENCE_THRESHOLD:
                premium_model = LLMRouter.model_for_task('fallback_extraction')
                logger.info('Photo analysis low confidence (%.2f) — escalating to %s', confidence, premium_model)
                retried = ProductPhotoAnalyzer._extract(client, data_uri, premium_model)
                if retried.get('is_product_photo'):
                    extraction = retried
                    model = premium_model
                    confidence = float(extraction.get('confidence') or confidence)

            if not extraction.get('is_product_photo'):
                return {
                    'ok': False,
                    'rejection_reason': extraction.get('rejection_reason') or 'unclear',
                    'category': '', 'suggested_title': '', 'description': '',
                    'attributes': [], 'confidence': 0.0, 'model_used': model,
                }

            copy = ProductPhotoAnalyzer._generate_copy(client, extraction, organization)

            return {
                'ok': True,
                'rejection_reason': None,
                'category': extraction.get('category') or '',
                'suggested_title': copy.get('title') or extraction.get('suggested_title') or '',
                'description': copy.get('description') or '',
                'attributes': extraction.get('attributes') or [],
                'confidence': confidence,
                'model_used': model,
            }
        except Exception as exc:
            logger.error('Product photo analysis failed: %s', exc)
            return ProductPhotoAnalyzer._unavailable()

    @staticmethod
    def _extract(client, data_uri: str, model: str) -> dict:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analiza esta foto de producto."},
                        {"type": "image_url", "image_url": {"url": data_uri, "detail": "low"}},
                    ],
                },
            ],
            temperature=0.2,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    @staticmethod
    def _generate_copy(client, extraction: dict, organization) -> dict:
        try:
            runtime_config = BrandVoice.load_runtime_config(organization)
            context_lines = BrandVoice.identity_lines(runtime_config)
        except Exception:
            context_lines = []

        context = '\n'.join(context_lines) if context_lines else 'Sin contexto de negocio adicional.'
        payload = {
            'category': extraction.get('category'),
            'attributes': extraction.get('attributes'),
            'suggested_title': extraction.get('suggested_title'),
        }
        model = LLMRouter.model_for_task('main_response')
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": COPY_SYSTEM_PROMPT},
                {"role": "user", "content": f"Contexto del negocio:\n{context}\n\nDatos detectados en la foto:\n{json.dumps(payload, ensure_ascii=False)}"},
            ],
            temperature=0.6,
            max_tokens=250,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    @staticmethod
    def _unavailable() -> dict:
        return {
            'ok': False,
            'rejection_reason': 'unavailable',
            'category': '', 'suggested_title': '', 'description': '',
            'attributes': [], 'confidence': 0.0, 'model_used': None,
        }
