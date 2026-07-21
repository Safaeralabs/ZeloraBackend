from __future__ import annotations

import io
from pathlib import Path

from rest_framework.exceptions import ValidationError

ALLOWED_PRODUCT_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_PRODUCT_IMAGE_MIME_TYPES = {
    'image/jpeg',
    'image/png',
    'image/webp',
}
MAX_PRODUCT_IMAGE_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024

# Photos destined for the vision model go through a stricter path: they must
# decode as real raster images (defeats disguised-file uploads), get their
# EXIF stripped (phone photos often carry embedded GPS), and get downscaled
# so a single analysis call stays cheap regardless of the original resolution.
MAX_PRODUCT_PHOTO_ANALYSIS_DIMENSION_PX = 1280


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


def normalize_product_photo_for_analysis(uploaded_file) -> bytes:
    """
    Validate + re-encode an uploaded photo before it ever reaches storage or
    the vision model.

    Re-encoding (rather than trusting the original bytes) is the actual
    security boundary here: Pillow has to successfully decode the file as an
    image, which rejects anything that merely has an image extension/MIME
    but isn't one (e.g. a script or archive renamed to .jpg). The re-save
    also drops EXIF (GPS/device metadata) and caps the resolution so one
    analysis call has a predictable, small token cost.
    """
    validate_product_image_upload(uploaded_file)

    from PIL import Image, UnidentifiedImageError

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image.verify()
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image = image.convert('RGB')
    except (UnidentifiedImageError, OSError):
        raise ValidationError('El archivo no es una imagen valida')

    image.thumbnail(
        (MAX_PRODUCT_PHOTO_ANALYSIS_DIMENSION_PX, MAX_PRODUCT_PHOTO_ANALYSIS_DIMENSION_PX),
        Image.LANCZOS,
    )

    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=88)  # no exif= kwarg -> metadata dropped
    return buffer.getvalue()
