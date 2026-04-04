from __future__ import annotations

from pathlib import Path

from rest_framework.exceptions import ValidationError

ALLOWED_KB_EXTENSIONS = {'.txt', '.md', '.pdf', '.docx', '.csv'}
ALLOWED_KB_MIME_TYPES = {
    'text/plain',
    'text/markdown',
    'text/csv',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}
MAX_KB_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024


def validate_kb_upload(uploaded_file) -> None:
    if uploaded_file is None:
        raise ValidationError('file is required')

    file_size = getattr(uploaded_file, 'size', 0) or 0
    if file_size <= 0:
        raise ValidationError('El archivo esta vacio')
    if file_size > MAX_KB_UPLOAD_SIZE_BYTES:
        raise ValidationError('El archivo supera el limite de 10 MB')

    extension = Path(getattr(uploaded_file, 'name', '')).suffix.lower()
    mime_type = (getattr(uploaded_file, 'content_type', '') or '').lower()

    if extension not in ALLOWED_KB_EXTENSIONS:
        raise ValidationError('Tipo de archivo no permitido')
    if mime_type and mime_type not in ALLOWED_KB_MIME_TYPES:
        raise ValidationError('MIME type no permitido')
