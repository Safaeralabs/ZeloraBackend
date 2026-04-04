# WhatsApp Real Setup

## Objetivo
Pasar de simulacion local a trafico real de Meta WhatsApp Cloud API.

## Lo que ya soporta el backend
- Webhook de verificacion:
  - `GET /api/channels/whatsapp/webhook/`
- Webhook de eventos:
  - `POST /api/channels/whatsapp/webhook/`
- Validacion de firma:
  - `X-Hub-Signature-256`
- Envio outbound via Cloud API:
  - `tasks.channel_tasks.send_whatsapp_message`
- Sync de templates:
  - `tasks.channel_tasks.sync_whatsapp_templates`

## Requisitos externos
- App de Meta creada
- WhatsApp Business Account del cliente
- Numero de telefono conectado en Cloud API
- `phone_number_id` real
- `waba_id` real
- `access_token` real
- `META_APP_SECRET` real
- webhook publico HTTPS

## Variables de entorno
Configura `backendv2/.env` con valores reales:

```env
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,<tu-dominio-publico>,<subdominio-ngrok>
CORS_ALLOWED_ORIGINS=http://localhost:5173,https://<tu-frontend-publico>

ENABLE_REAL_WHATSAPP=True
META_APP_ID=<meta_app_id>
META_APP_SECRET=<meta_app_secret>
WHATSAPP_VERIFY_TOKEN=<verify_token_seguro>
WHATSAPP_API_VERSION=v19.0
WHATSAPP_BASE_URL=https://graph.facebook.com
```

## Infra necesaria
Para trafico real no basta con `runserver`.

Necesitas:
- backend publico por HTTPS
- Redis levantado
- Celery worker levantado

Minimo:
1. exponer backend con `ngrok` o desplegar staging
2. tener Redis accesible para Celery
3. levantar worker:

```powershell
cd C:\Users\afper\Proyectos\Vendly\backendv2
.venv\Scripts\python.exe -m celery -A config worker -l info -Q channels,campaigns,ai
```

## Configuracion en Meta
En la app de Meta:
1. entra a WhatsApp > Configuration
2. configura el webhook callback URL:
   - `https://<tu-host-publico>/api/channels/whatsapp/webhook/`
3. usa el mismo `WHATSAPP_VERIFY_TOKEN`
4. suscribe el app a eventos de WhatsApp
5. asegúrate de tener vinculado el numero correcto

## Configuracion en Vendly
En `/whatsapp` guarda:
- `access_token`
- `phone_number_id`
- `whatsapp_business_account_id`
- `display_phone_number`
- `verified_name`
- `is_active=true`

Despues:
- ejecuta `Verify webhook`
- ejecuta `Sync templates`

## Flujo de prueba real
### Caso A: numero de prueba de Meta
- solo podras escribir desde numeros permitidos por Meta
- sirve para validar inbound y outbound reales

### Caso B: numero productivo del cliente
- cualquier usuario puede escribir al numero
- outbound libre solo dentro de la ventana de 24 horas
- fuera de esa ventana, usa templates aprobados

## Verificacion recomendada
1. usuario escribe al numero real
2. Meta llama tu webhook
3. se crea/actualiza `Contact`
4. se crea/actualiza `Conversation`
5. aparece en `/inbox`
6. respondes desde inbox
7. Meta entrega el mensaje
8. llega callback de estado y se actualiza metadata

## Qué mirar si falla
- `backendv2/logs/vendly.json.log`
- respuesta de Meta en logs `whatsapp_send_http_error`
- error de firma en webhook
- `Unknown phone number binding`
- worker de Celery caido
- Redis caido

## Limitaciones actuales a tener en cuenta
- el panel `/whatsapp` no hace Embedded Signup real todavia
- el webhook ya esta listo, pero necesitas host publico real
- para produccion real conviene encriptar `access_token` en reposo
