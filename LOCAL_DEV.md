# Backendv2 Local MVP

## Prerequisites
- Python environment: `backendv2/.venv`
- Local settings file: `backendv2/.env`

## First-time setup
```powershell
C:\Users\afper\Proyectos\Vendly\backendv2\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
C:\Users\afper\Proyectos\Vendly\backendv2\.venv\Scripts\python.exe manage.py migrate --run-syncdb
C:\Users\afper\Proyectos\Vendly\backendv2\.venv\Scripts\python.exe manage.py seed_mvp
```

## Run backend
```powershell
C:\Users\afper\Proyectos\Vendly\backendv2\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

## Smoke tests
```powershell
C:\Users\afper\Proyectos\Vendly\backendv2\.venv\Scripts\python.exe manage.py test apps.channels_config.tests.test_mvp_smoke -v 2
```

## Seeded MVP credentials
- Email: `admin@comfaguajira.com`
- Password: `Admin1234!`

## Local runtime assumptions
- SQLite enabled
- In-memory channel layer enabled
- Local memory cache enabled
- Celery eager mode enabled
- `ENABLE_REAL_WHATSAPP=False`

## Frontend real mode
- File: `frontend/.env.local`
- Required value: `VITE_USE_MOCK_DATA=false`
