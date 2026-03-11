# Vendly Backend — Django config package
# This tells Celery to use the tasks.celery_app module when running from the Django project root.
# The actual Celery app is defined in tasks/celery_app.py.
# This import ensures the @shared_task decorator works in all Django apps.
from tasks.celery_app import app as celery_app  # noqa: F401

__all__ = ('celery_app',)
