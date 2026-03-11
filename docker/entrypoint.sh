#!/bin/bash
# ─── Vendly API Entrypoint ──────────────────────────────────────────────────────
# 1. Wait for PostgreSQL to be ready
# 2. Run Django migrations
# 3. Collect static files
# 4. Execute the CMD (gunicorn)
set -e

# ─── Wait for PostgreSQL ────────────────────────────────────────────────────────
echo "⏳ Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
until python -c "
import sys, psycopg2
try:
    psycopg2.connect(
        host='${DB_HOST:-postgres}',
        port='${DB_PORT:-5432}',
        dbname='${DB_NAME:-vendly_db}',
        user='${DB_USER:-vendly_user}',
        password='${DB_PASSWORD:-vendly_pass}',
        connect_timeout=3,
    )
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    printf '.'
    sleep 1
done
echo ""
echo "✅ PostgreSQL is ready."

# ─── Django Migrations ──────────────────────────────────────────────────────────
echo "🔄 Running migrations..."
python manage.py migrate --noinput

# ─── Collect Static Files ────────────────────────────────────────────────────────
echo "📦 Collecting static files..."
python manage.py collectstatic --noinput --clear

# ─── Create superuser if not exists (dev/staging bootstrap) ────────────────────
if [ "${CREATE_SUPERUSER:-false}" = "true" ]; then
    echo "👤 Creating superuser..."
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='${SUPERUSER_EMAIL:-admin@vendly.ai}').exists():
    User.objects.create_superuser(
        email='${SUPERUSER_EMAIL:-admin@vendly.ai}',
        password='${SUPERUSER_PASSWORD:-admin123}',
        nombre='Admin',
    )
    print('Superuser created.')
else:
    print('Superuser already exists.')
" 2>/dev/null || true
fi

echo "🚀 Starting server..."
exec "$@"
