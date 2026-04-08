from __future__ import annotations

from pathlib import Path

from rest_framework.exceptions import ValidationError

ALLOWED_PRODUCT_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_PRODUCT_IMAGE_MIME_TYPES = {
    'image/jpeg',
    'image/png',
    'image/webp',
}
MAX_PRODUCT_IMAGE_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024


def validate_product_image_upload(uploaded_file) -> None:
    if uploaded_file is None:
        raise ValidationError('file is required')

    file_size = getattr(uploaded_file, 'size', 0) or 0
    if file_size <= 0:
        raise ValidationError('La imagen esta vacia')
    if file_size > MAX_PRODUCT_IMAGE_UPLOAD_SIZE_BYTES:
        raise ValidationError('La imagen supera el limite de 5 MB')

    extension = Path(getattr(uploaded_file, 'name', '')).suffix.lower()
    mime_type = (getattr(uploaded_file, 'content_type', '') or '').lower()

    if extension not in ALLOWED_PRODUCT_IMAGE_EXTENSIONS:
        raise ValidationError('Formato de imagen no permitido')
    if mime_type and mime_type not in ALLOWED_PRODUCT_IMAGE_MIME_TYPES:
        raise ValidationError('Tipo MIME de imagen no permitido')
