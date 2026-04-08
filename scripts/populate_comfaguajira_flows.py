"""
Populate Comfaguajira flows and intents from PDF (Tarifario 2026) + chat analysis.

Run from backendv2/:
    py manage.py shell < scripts/populate_comfaguajira_flows.py
Or:
    py -c "exec(open('scripts/populate_comfaguajira_flows.py').read())"
"""
import os, sys, django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.accounts.models import Organization
from apps.flows.models import Flow, CustomIntent

ORG_ID = 'd620ebfb-71b3-48f6-ab9e-1f187f93d9fb'

try:
    org = Organization.objects.get(id=ORG_ID)
except Organization.DoesNotExist:
    print(f'ERROR: Organization {ORG_ID} not found.')
    sys.exit(1)

print(f'Organization: {org}')

# ─── Wipe existing data for idempotency ────────────────────────────────────────
deleted_flows, _ = Flow.objects.filter(organization=org).delete()
deleted_intents, _ = CustomIntent.objects.filter(organization=org).delete()
print(f'Deleted {deleted_flows} flows and {deleted_intents} intents.')

# ─── INTENTS ───────────────────────────────────────────────────────────────────

INTENTS = [
    {
        'name': 'consulta_subsidio_familiar',
        'label': 'Consulta Subsidio Familiar',
        'keywords': [
            'subsidio', 'subsidio familiar', 'cuanto es el subsidio',
            'cobrar subsidio', 'pago de subsidio', 'subsidio en especie',
            'subsidio en dinero', 'reclamar subsidio', 'valor subsidio',
        ],
    },
    {
        'name': 'cambio_medio_pago',
        'label': 'Cambio de Medio de Pago',
        'keywords': [
            'cambiar cuenta', 'cambio de cuenta', 'cambiar cuenta bancaria',
            'actualizar cuenta', 'medio de pago', 'cuenta nómina', 'daviplata',
            'nequi', 'cambio banco', 'banco', 'número de cuenta',
        ],
    },
    {
        'name': 'consulta_afiliacion',
        'label': 'Consulta de Afiliación',
        'keywords': [
            'afiliarme', 'como me afilio', 'afiliación', 'afiliacion',
            'afiliado', 'empresa afiliada', 'requisitos afiliacion',
            'estoy afiliado', 'registrarme', 'inscribir empresa',
        ],
    },
    {
        'name': 'solicitud_certificado',
        'label': 'Solicitud de Certificado',
        'keywords': [
            'certificado', 'certificados', 'paz y salvo', 'constancia',
            'carta de afiliación', 'carta afiliacion', 'certificado laboral',
            'certificado subsidio', 'descarga certificado',
        ],
    },
    {
        'name': 'consulta_credito',
        'label': 'Consulta Crédito Social',
        'keywords': [
            'crédito', 'credito', 'préstamo', 'prestamo', 'financiamiento',
            'credicomfaguajira', 'credi', 'cuotas', 'tasa de interés',
            'solicitar crédito', 'credito educativo', 'credito vivienda',
        ],
    },
    {
        'name': 'consulta_recreacion',
        'label': 'Consulta de Recreación',
        'keywords': [
            'recreacion', 'recreación', 'piscina', 'parque', 'gimnasio',
            'actividades recreativas', 'deporte', 'club comfaguajira',
            'espacios recreativos', 'canchas', 'programa recreativo',
        ],
    },
    {
        'name': 'consulta_vivienda',
        'label': 'Subsidio de Vivienda',
        'keywords': [
            'vivienda', 'subsidio vivienda', 'casa', 'comprar casa',
            'financiar vivienda', 'subsidio habitacional', 'vis',
            'mejoramiento vivienda', 'construir casa',
        ],
    },
    {
        'name': 'consulta_foninez',
        'label': 'Consulta FONINEZ',
        'keywords': [
            'foninez', 'niñez', 'niños', 'infancia', 'jardín infantil',
            'jardin', 'educacion inicial', 'primera infancia', 'guardian',
        ],
    },
    {
        'name': 'consulta_turismo',
        'label': 'Consulta de Turismo',
        'keywords': [
            'turismo', 'viaje', 'vacaciones', 'tour', 'paquete',
            'plan vacacional', 'destino', 'hotel', 'crucero', 'paseo',
        ],
    },
    {
        'name': 'consulta_educacion',
        'label': 'Consulta de Educación',
        'keywords': [
            'educacion', 'educación', 'beca', 'capacitacion', 'capacitación',
            'curso', 'talleres', 'subsidio educativo', 'estudiar', 'formacion',
        ],
    },
]

created_intents = 0
for intent_data in INTENTS:
    CustomIntent.objects.create(
        organization=org,
        name=intent_data['name'],
        label=intent_data['label'],
        keywords=intent_data['keywords'],
        is_active=True,
    )
    created_intents += 1

print(f'Created {created_intents} intents.')

# ─── FLOW HELPERS ──────────────────────────────────────────────────────────────

META_ID = '__flow_meta__'

def meta_node(trigger_type, keywords=None, intent=None, canales=None):
    return {
        'id': META_ID,
        'tipo': '__meta__',
        'router_config': {
            'triggerType': trigger_type,
            'intent': intent or 'unknown',
            'keywords': keywords or [],
            'confidenceThreshold': 0.8,
            'fallbackAction': 'request_clarification',
        },
        'canales': canales or ['whatsapp'],
    }

def node(nid, tipo, **data_kwargs):
    return {'id': nid, 'tipo': tipo, 'data': data_kwargs}

def edge(eid, source, target, condition='default'):
    return {'id': eid, 'source': source, 'target': target, 'data': {'condition': condition}}

# ─── FLOW 1: BIENVENIDA Y MENÚ PRINCIPAL ──────────────────────────────────────

flow1_nodes = [
    node('n1', 'start'),
    node('n2', 'message', text=(
        'Hola {{contact_name}}! 👋 Bienvenido al asistente virtual de *Comfaguajira*.\n'
        'Estoy aquí para orientarte con nuestros servicios y beneficios.'
    )),
    node('n3', 'quickReply',
        text='¿En qué puedo ayudarte hoy?',
        options=[
            'Subsidio Familiar',
            'Crédito Social',
            'Recreación y Turismo',
            'Certificados y Trámites',
            'Hablar con un asesor',
        ],
        variable='menu_opcion',
    ),
    node('n4', 'condition',
        variable='menu_opcion',
        operator='eq',
        value='Hablar con un asesor',
    ),
    node('n5', 'escalate',
        text='Entendido. En un momento un asesor de Comfaguajira te atenderá. 🙏',
        reason='solicitó_asesor_desde_menu',
    ),
    node('n6', 'ai_reply'),
    meta_node('keyword',
        keywords=['hola', 'buenos dias', 'buenas tardes', 'buenas noches',
                  'inicio', 'menu', 'menú', 'empezar', 'comenzar', 'start'],
        canales=['web', 'app'],
    ),
]

flow1_edges = [
    edge('e1', 'n1', 'n2'),
    edge('e2', 'n2', 'n3'),
    edge('e3', 'n3', 'n4'),
    edge('e4', 'n4', 'n5', condition='yes'),
    edge('e5', 'n4', 'n6', condition='no'),
]

Flow.objects.create(
    organization=org,
    name='Bienvenida y Menú Principal',
    description='Saludo inicial y menú de opciones. Se activa con palabras clave de inicio.',
    nodes=flow1_nodes,
    edges=flow1_edges,
    trigger='keyword',
    channel='web',
    is_active=True,
)

# ─── FLOW 2: CONSULTA SUBSIDIO FAMILIAR ───────────────────────────────────────

flow2_nodes = [
    node('n1', 'start'),
    node('n2', 'message', text=(
        'Con gusto te explico sobre el *Subsidio Familiar* de Comfaguajira. 📋\n\n'
        'El subsidio familiar es un auxilio económico mensual que reciben los trabajadores '
        'afiliados con ingresos de hasta 4 SMMLV (salarios mínimos).\n\n'
        '*Modalidades disponibles:*\n'
        '• 💵 En dinero: pago mensual directo\n'
        '• 📦 En especie: productos de la canasta familiar\n'
        '• 🎓 En servicios: educación, recreación, vivienda'
    )),
    node('n3', 'quickReply',
        text='¿Qué aspecto del subsidio te interesa?',
        options=[
            '¿Cuánto me corresponde?',
            '¿Cómo lo cobro?',
            '¿Quiénes son beneficiarios?',
            '¿Cómo cambio mi forma de pago?',
        ],
        variable='subsidio_opcion',
    ),
    node('n4', 'condition',
        variable='subsidio_opcion',
        operator='eq',
        value='¿Cuánto me corresponde?',
    ),
    node('n5', 'message', text=(
        '*Tarifas del Subsidio en Dinero 2026:*\n\n'
        '• Hasta 1 SMMLV: $56.000/mes por carga\n'
        '• De 1 a 2 SMMLV: $56.000/mes por carga\n'
        '• De 2 a 3 SMMLV: $28.000/mes por carga\n'
        '• De 3 a 4 SMMLV: $14.000/mes por carga\n\n'
        '_Las cargas son hijos u otras personas dependientes debidamente registradas._\n\n'
        'Para conocer tu valor exacto ingresa a *comfaguajira.com.co* o llama al *601-123-4567*.'
    )),
    node('n6', 'condition',
        variable='subsidio_opcion',
        operator='eq',
        value='¿Cómo lo cobro?',
    ),
    node('n7', 'message', text=(
        '*¿Cómo cobrar tu subsidio?*\n\n'
        '1. El subsidio en dinero se paga directamente en tu cuenta bancaria o nómina.\n'
        '2. Si no tienes cuenta registrada, puedes recibirlo en Daviplata o Nequi.\n'
        '3. Para el subsidio en especie, dirígete a cualquier sede de Comfaguajira.\n\n'
        '📌 *Importante:* El empleador es quien realiza el giro. '
        'Si llevas más de 2 meses sin recibirlo, comunícate con nosotros.'
    )),
    node('n8', 'message', text=(
        '*Beneficiarios del Subsidio Familiar:*\n\n'
        '✅ Hijos menores de 18 años\n'
        '✅ Hijos entre 18 y 23 años que estudian\n'
        '✅ Hijos con discapacidad (sin límite de edad)\n'
        '✅ Padres o hermanos a cargo del trabajador\n\n'
        '_Todos los beneficiarios deben estar registrados en tu afiliación._'
    )),
    node('n9', 'message', text=(
        '*Cambio de Medio de Pago del Subsidio:*\n\n'
        'Para actualizar tu cuenta de cobro:\n'
        '1. Ingresa a *comfaguajira.com.co* → "Mi Portal"\n'
        '2. O visita cualquier sede con tu cédula y certificación bancaria\n'
        '3. O escribe "cambiar cuenta" para que te asistamos ahora\n\n'
        '⏱ El cambio aplica a partir del siguiente periodo de pago.'
    )),
    node('n10', 'message', text=(
        '¿Hay algo más en lo que pueda ayudarte? Puedes escribir tu consulta o escribir *menú* para ver las opciones.'
    )),
    node('n11', 'end', message=''),
    meta_node('keyword',
        intent='consulta_subsidio_familiar',
        keywords=['subsidio', 'subsidio familiar', 'cuanto es el subsidio',
                  'cobrar subsidio', 'pago subsidio', 'reclamar subsidio'],
        canales=['web', 'app'],
    ),
]

flow2_edges = [
    edge('e1', 'n1', 'n2'),
    edge('e2', 'n2', 'n3'),
    edge('e3', 'n3', 'n4'),
    edge('e4', 'n4', 'n5', condition='yes'),
    edge('e5', 'n4', 'n6', condition='no'),
    edge('e6', 'n6', 'n7', condition='yes'),
    edge('e7', 'n6', 'n8', condition='no'),
    edge('e8', 'n5', 'n10'),
    edge('e9', 'n7', 'n10'),
    edge('e10', 'n8', 'n10'),
    edge('e11', 'n9', 'n10'),
    # Default branch for "¿Cómo cambio mi forma de pago?" goes to n9
    edge('e12', 'n3', 'n9', condition='option:¿Cómo cambio mi forma de pago?'),
    edge('e13', 'n10', 'n11'),
]

Flow.objects.create(
    organization=org,
    name='Consulta Subsidio Familiar',
    description='Información sobre subsidio familiar: montos, beneficiarios, cobro y cambio de medio de pago.',
    nodes=flow2_nodes,
    edges=flow2_edges,
    trigger='consulta_subsidio_familiar',
    channel='web',
    is_active=True,
)

# ─── FLOW 3: TRÁMITE CRÉDITO SOCIAL ───────────────────────────────────────────

flow3_nodes = [
    node('n1', 'start'),
    node('n2', 'message', text=(
        'Te cuento sobre los *Créditos Sociales de Comfaguajira* 💳\n\n'
        'Ofrecemos créditos con condiciones preferenciales para afiliados activos:\n\n'
        '• 🎓 Crédito Educativo\n'
        '• 🏠 Crédito para Vivienda\n'
        '• 💊 Crédito para Salud\n'
        '• 🛒 Crédito de Consumo\n'
        '• 📦 Crédito en Especie (electrodomésticos, muebles)'
    )),
    node('n3', 'quickReply',
        text='¿Qué tipo de crédito te interesa?',
        options=[
            'Crédito Educativo',
            'Crédito Vivienda',
            'Crédito Consumo',
            'Conocer requisitos generales',
        ],
        variable='tipo_credito',
    ),
    node('n4', 'condition',
        variable='tipo_credito',
        operator='eq',
        value='Crédito Educativo',
    ),
    node('n5', 'message', text=(
        '*Crédito Educativo Comfaguajira:*\n\n'
        '• Montos desde $500.000 hasta $15.000.000\n'
        '• Plazo hasta 24 meses\n'
        '• Tasa preferencial para afiliados\n'
        '• Para: matrícula, útiles, uniformes, cursos técnicos\n\n'
        '*Requisitos:* Ser afiliado activo, paz y salvo con Comfaguajira, '
        'recibo de matrícula o constancia de estudio.'
    )),
    node('n6', 'condition',
        variable='tipo_credito',
        operator='eq',
        value='Crédito Vivienda',
    ),
    node('n7', 'message', text=(
        '*Crédito para Vivienda:*\n\n'
        '• Complementario al subsidio de vivienda\n'
        '• Montos según capacidad de pago\n'
        '• Plazos hasta 60 meses\n'
        '• Para: compra, mejoramiento o construcción de vivienda\n\n'
        '*Requisitos:* Afiliado activo con mínimo 6 meses, '
        'documentos del inmueble, certificación de ingresos.'
    )),
    node('n8', 'message', text=(
        '*Crédito de Consumo:*\n\n'
        '• Montos desde $200.000 hasta $8.000.000\n'
        '• Plazos de 3 a 18 meses\n'
        '• Desembolso en 48-72 horas hábiles\n'
        '• Para cualquier necesidad del afiliado\n\n'
        '*Requisitos:* Afiliado activo, cédula de ciudadanía, '
        'últimas 2 colillas de pago.'
    )),
    node('n9', 'message', text=(
        '*Requisitos generales para créditos Comfaguajira:*\n\n'
        '✅ Ser trabajador afiliado activo\n'
        '✅ Cédula de ciudadanía vigente\n'
        '✅ Certificado de afiliación al día\n'
        '✅ Paz y salvo con Comfaguajira\n'
        '✅ Últimas 2 colillas de pago\n\n'
        '📍 Radica tu solicitud en cualquier sede o en *comfaguajira.com.co*'
    )),
    node('n10', 'collect',
        text='¿Te gustaría que un asesor de crédito te contacte? Si sí, escribe tu *número de cédula*:',
        variable='cedula_credito',
        input_type='text',
    ),
    node('n11', 'message', text=(
        'Gracias. Hemos registrado tu consulta con cédula *{{cedula_credito}}*. '
        'Un asesor de Comfaguajira se comunicará contigo en las próximas 24 horas hábiles. 📞'
    )),
    node('n12', 'end', message=''),
    meta_node('keyword',
        intent='consulta_credito',
        keywords=['crédito', 'credito', 'préstamo', 'prestamo', 'credi',
                  'financiamiento', 'cuotas', 'tasa de interés', 'credicomfaguajira'],
        canales=['web', 'app'],
    ),
]

flow3_edges = [
    edge('e1', 'n1', 'n2'),
    edge('e2', 'n2', 'n3'),
    edge('e3', 'n3', 'n4'),
    edge('e4', 'n4', 'n5', condition='yes'),
    edge('e5', 'n4', 'n6', condition='no'),
    edge('e6', 'n6', 'n7', condition='yes'),
    edge('e7', 'n6', 'n8', condition='no'),
    edge('e8', 'n3', 'n9', condition='option:Conocer requisitos generales'),
    edge('e9', 'n5', 'n10'),
    edge('e10', 'n7', 'n10'),
    edge('e11', 'n8', 'n10'),
    edge('e12', 'n9', 'n10'),
    edge('e13', 'n10', 'n11'),
    edge('e14', 'n11', 'n12'),
]

Flow.objects.create(
    organization=org,
    name='Trámite Crédito Social',
    description='Información sobre líneas de crédito social: educativo, vivienda, consumo. Captura cédula para seguimiento.',
    nodes=flow3_nodes,
    edges=flow3_edges,
    trigger='consulta_credito',
    channel='web',
    is_active=True,
)

# ─── FLOW 4: RECREACIÓN Y TURISMO ─────────────────────────────────────────────

flow4_nodes = [
    node('n1', 'start'),
    node('n2', 'message', text=(
        '¡Conoce todos los beneficios de *Recreación y Turismo* de Comfaguajira! 🎉\n\n'
        'Como afiliado y tu familia tienen acceso preferencial a nuestros espacios '
        'y programas recreativos.'
    )),
    node('n3', 'quickReply',
        text='¿Qué te interesa conocer?',
        options=[
            'Piscinas y parques',
            'Planes vacacionales',
            'Turismo nacional',
            'Programas para niños',
        ],
        variable='recreacion_opcion',
    ),
    node('n4', 'condition',
        variable='recreacion_opcion',
        operator='eq',
        value='Piscinas y parques',
    ),
    node('n5', 'message', text=(
        '*Centros Recreativos Comfaguajira:*\n\n'
        '🏊 *Piscinas:* Disponibles en sedes Riohacha, Maicao y Uribia\n'
        '⏰ Horario: Lunes a viernes 6am-6pm | Sábados 7am-5pm\n\n'
        '*Tarifas 2026 (afiliados):*\n'
        '• Adulto afiliado: $8.000\n'
        '• Niño beneficiario: $5.000\n'
        '• Adulto mayor afiliado: $4.000\n\n'
        '*No afiliados:* tarifa plena ($15.000 adulto / $10.000 niño)'
    )),
    node('n6', 'condition',
        variable='recreacion_opcion',
        operator='eq',
        value='Planes vacacionales',
    ),
    node('n7', 'message', text=(
        '*Planes Vacacionales Comfaguajira 2026:*\n\n'
        '🌴 Disponibles en enero, julio y diciembre\n'
        '👶 Grupos de 5 a 12 años\n'
        '📅 Duración: 2 semanas por periodo\n\n'
        '*Incluye:* Actividades lúdicas, deportes, manualidades, '
        'excursiones locales y alimentación.\n\n'
        '*Inscripciones:* Comienzan 30 días antes en sedes o en línea.\n'
        '📍 Cupos limitados — ¡inscríbete pronto!'
    )),
    node('n8', 'condition',
        variable='recreacion_opcion',
        operator='eq',
        value='Turismo nacional',
    ),
    node('n9', 'message', text=(
        '*Turismo con Comfaguajira:*\n\n'
        '✈️ Paquetes turísticos con tarifas preferenciales para afiliados\n\n'
        '*Destinos populares 2026:*\n'
        '• 🏝 Cabo de la Vela y Punta Gallinas (La Guajira)\n'
        '• 🏖 Cartagena — paquetes 3 y 4 noches\n'
        '• 🌿 Santa Marta y Parque Tayrona\n'
        '• 🏔 San Andrés — especial temporada alta\n\n'
        'Consulta precios y fechas disponibles en *comfaguajira.com.co/turismo* '
        'o llama al área de turismo.'
    )),
    node('n10', 'message', text=(
        '*Programas para Niños:*\n\n'
        '🎨 Talleres de arte y manualidades\n'
        '⚽ Escuelas deportivas (fútbol, baloncesto, natación)\n'
        '💻 Cursos de tecnología e informática\n'
        '🎭 Teatro y expresión corporal\n\n'
        '📅 Programas regulares: Sábados 8am-12m\n'
        'Inscripciones abiertas en cualquier sede Comfaguajira.'
    )),
    node('n11', 'message', text=(
        'Para más información visita *comfaguajira.com.co* o acércate a cualquier sede.\n'
        '¿Hay algo más en lo que pueda ayudarte?'
    )),
    node('n12', 'end', message=''),
    meta_node('keyword',
        intent='consulta_recreacion',
        keywords=['recreacion', 'recreación', 'piscina', 'parque', 'turismo',
                  'vacaciones', 'viaje', 'planes vacacionales', 'niños actividades',
                  'gimnasio', 'deporte', 'comfaguajira piscina'],
        canales=['web', 'app'],
    ),
]

flow4_edges = [
    edge('e1', 'n1', 'n2'),
    edge('e2', 'n2', 'n3'),
    edge('e3', 'n3', 'n4'),
    edge('e4', 'n4', 'n5', condition='yes'),
    edge('e5', 'n4', 'n6', condition='no'),
    edge('e6', 'n6', 'n7', condition='yes'),
    edge('e7', 'n6', 'n8', condition='no'),
    edge('e8', 'n8', 'n9', condition='yes'),
    edge('e9', 'n8', 'n10', condition='no'),
    edge('e10', 'n3', 'n10', condition='option:Programas para niños'),
    edge('e11', 'n5', 'n11'),
    edge('e12', 'n7', 'n11'),
    edge('e13', 'n9', 'n11'),
    edge('e14', 'n10', 'n11'),
    edge('e15', 'n11', 'n12'),
]

Flow.objects.create(
    organization=org,
    name='Recreación y Turismo',
    description='Información sobre piscinas, planes vacacionales, turismo nacional y programas para niños.',
    nodes=flow4_nodes,
    edges=flow4_edges,
    trigger='consulta_recreacion',
    channel='web',
    is_active=True,
)

# ─── FLOW 5: SOLICITUD DE CERTIFICADOS ────────────────────────────────────────

flow5_nodes = [
    node('n1', 'start'),
    node('n2', 'message', text=(
        'Puedo ayudarte con la *descarga y solicitud de certificados* de Comfaguajira. 📄'
    )),
    node('n3', 'quickReply',
        text='¿Qué certificado necesitas?',
        options=[
            'Certificado de afiliación',
            'Paz y salvo',
            'Certificado de subsidio',
            'Carta laboral para trámites',
        ],
        variable='tipo_certificado',
    ),
    node('n4', 'message', text=(
        '*Cómo obtener tu certificado:*\n\n'
        '🖥 *Opción 1 (más rápida):* Descarga en línea\n'
        '1. Ingresa a *comfaguajira.com.co*\n'
        '2. Ve a "Mi Portal" → "Documentos"\n'
        '3. Selecciona el certificado → Descarga PDF\n\n'
        '📱 *Opción 2:* App Comfaguajira (disponible en Play Store / App Store)\n\n'
        '🏢 *Opción 3:* En cualquier sede con tu cédula\n'
        '⏱ Entrega inmediata en sede | En línea: disponible 24/7\n\n'
        '_Si el certificado no aparece en línea, puede que tu afiliación '
        'requiera actualización — comunícate con nosotros._'
    )),
    node('n5', 'collect',
        text='¿Pudiste obtener el certificado? Si tienes algún inconveniente, escríbeme y te ayudo.',
        variable='pudo_obtener',
        input_type='text',
    ),
    node('n6', 'condition',
        variable='pudo_obtener',
        operator='contains',
        value='no',
    ),
    node('n7', 'escalate',
        text='Entendido. Te voy a conectar con un asesor para que te ayude a resolver el inconveniente. 🙏',
        reason='problema_certificado',
    ),
    node('n8', 'end', message='¡Perfecto! Si necesitas algo más, con gusto te ayudo. 😊'),
    meta_node('keyword',
        intent='solicitud_certificado',
        keywords=['certificado', 'paz y salvo', 'constancia', 'carta afiliacion',
                  'carta de afiliación', 'certificado subsidio', 'descargar certificado'],
        canales=['web', 'app'],
    ),
]

flow5_edges = [
    edge('e1', 'n1', 'n2'),
    edge('e2', 'n2', 'n3'),
    edge('e3', 'n3', 'n4'),
    edge('e4', 'n4', 'n5'),
    edge('e5', 'n5', 'n6'),
    edge('e6', 'n6', 'n7', condition='yes'),
    edge('e7', 'n6', 'n8', condition='no'),
]

Flow.objects.create(
    organization=org,
    name='Certificados y Trámites',
    description='Guía para obtener certificados de afiliación, paz y salvo y subsidio. Escala si hay problemas.',
    nodes=flow5_nodes,
    edges=flow5_edges,
    trigger='solicitud_certificado',
    channel='web',
    is_active=True,
)

# ─── FLOW 6: ESCALADO A AGENTE HUMANO ─────────────────────────────────────────

flow6_nodes = [
    node('n1', 'start'),
    node('n2', 'message', text='Voy a conectarte con un asesor de Comfaguajira. Por favor dame un momento. 🙏'),
    node('n3', 'collect',
        text='Para agilizar la atención, ¿me puedes indicar brevemente el motivo de tu consulta?',
        variable='motivo_consulta',
        input_type='text',
    ),
    node('n4', 'escalate',
        text='Gracias. Un asesor estará contigo en breve para ayudarte con: *{{motivo_consulta}}*',
        reason='solicitud_directa_asesor',
    ),
    meta_node('keyword',
        keywords=[
            'hablar con asesor', 'asesor', 'agente', 'persona', 'humano',
            'ayuda especializada', 'hablar con alguien', 'quiero hablar',
            'comunicarme con', 'necesito un asesor',
        ],
        canales=['web', 'app'],
    ),
]

flow6_edges = [
    edge('e1', 'n1', 'n2'),
    edge('e2', 'n2', 'n3'),
    edge('e3', 'n3', 'n4'),
]

Flow.objects.create(
    organization=org,
    name='Escalado a Asesor Humano',
    description='Transfiere la conversación a un asesor humano cuando el usuario lo solicita explícitamente.',
    nodes=flow6_nodes,
    edges=flow6_edges,
    trigger='keyword',
    channel='web',
    is_active=True,
)

# ─── FLOW 7: CONSULTA AFILIACIÓN ──────────────────────────────────────────────

flow7_nodes = [
    node('n1', 'start'),
    node('n2', 'message', text=(
        'Te explico cómo funciona la *afiliación a Comfaguajira*. 📋\n\n'
        'Comfaguajira es la Caja de Compensación Familiar de La Guajira. '
        'La afiliación la realiza el *empleador* (empresa) por cada trabajador contratado.'
    )),
    node('n3', 'quickReply',
        text='¿Qué necesitas saber sobre afiliación?',
        options=[
            'Soy trabajador — ¿cómo me afilio?',
            'Soy empleador — ¿cómo afilio mi empresa?',
            'Verificar si estoy afiliado',
            'Actualizar mis datos',
        ],
        variable='afiliacion_opcion',
    ),
    node('n4', 'condition',
        variable='afiliacion_opcion',
        operator='eq',
        value='Soy trabajador — ¿cómo me afilio?',
    ),
    node('n5', 'message', text=(
        '*Si eres trabajador:*\n\n'
        'La afiliación la hace tu empleador de forma automática al contratarte.\n\n'
        '✅ Si tienes contrato de trabajo, tu empresa debe afiliarte a una caja de compensación.\n'
        '✅ Pide a tu empleador que te afilie a *Comfaguajira*.\n\n'
        'Una vez afiliado, recibirás:\n'
        '• Tu carnet de afiliado\n'
        '• Acceso al portal Mi Comfaguajira\n'
        '• Todos los beneficios: subsidio, recreación, créditos, salud, educación'
    )),
    node('n6', 'condition',
        variable='afiliacion_opcion',
        operator='eq',
        value='Soy empleador — ¿cómo afilio mi empresa?',
    ),
    node('n7', 'message', text=(
        '*Afiliación para Empleadores:*\n\n'
        '1. Ingresa a *comfaguajira.com.co* → "Empresas"\n'
        '2. O visita nuestra sede principal en Riohacha\n\n'
        '*Documentos necesarios:*\n'
        '• RUT de la empresa\n'
        '• Cámara de comercio\n'
        '• Cédula del representante legal\n'
        '• Relación de trabajadores (nombre, cédula, salario)\n\n'
        '📞 Asesoría empresarial: llama a nuestro conmutador o escribe al correo empresas@comfaguajira.com.co'
    )),
    node('n8', 'message', text=(
        '*Verificar tu afiliación:*\n\n'
        '🖥 Ingresa a *comfaguajira.com.co* → "Mi Portal"\n'
        'Ingresa con tu número de cédula.\n\n'
        'Si no apareces en el sistema, puede ser porque:\n'
        '• Tu empleador aún no te ha afiliado\n'
        '• Tu afiliación está inactiva (no tienes empleador activo)\n'
        '• Necesitas actualizar tus datos\n\n'
        'En cualquiera de esos casos, un asesor puede ayudarte.'
    )),
    node('n9', 'message', text=(
        '*Actualización de datos:*\n\n'
        'Para actualizar tus datos personales (teléfono, dirección, beneficiarios):\n\n'
        '1. Portal web: *comfaguajira.com.co* → "Mi Portal" → "Mis datos"\n'
        '2. En sede: presenta tu cédula y el dato a actualizar\n'
        '3. Vía WhatsApp: escribe a nuestro número oficial y adjunta el soporte del cambio\n\n'
        '⚠️ Para cambios de beneficiarios se requiere documentación adicional.'
    )),
    node('n10', 'end', message='¿Tienes alguna otra duda? Estoy aquí para ayudarte. 😊'),
    meta_node('keyword',
        intent='consulta_afiliacion',
        keywords=['afiliarme', 'como me afilio', 'afiliación', 'afiliacion',
                  'afiliado', 'empresa afiliada', 'estoy afiliado', 'registrarme'],
        canales=['web', 'app'],
    ),
]

flow7_edges = [
    edge('e1', 'n1', 'n2'),
    edge('e2', 'n2', 'n3'),
    edge('e3', 'n3', 'n4'),
    edge('e4', 'n4', 'n5', condition='yes'),
    edge('e5', 'n4', 'n6', condition='no'),
    edge('e6', 'n6', 'n7', condition='yes'),
    edge('e7', 'n6', 'n8', condition='no'),
    edge('e8', 'n3', 'n9', condition='option:Actualizar mis datos'),
    edge('e9', 'n5', 'n10'),
    edge('e10', 'n7', 'n10'),
    edge('e11', 'n8', 'n10'),
    edge('e12', 'n9', 'n10'),
]

Flow.objects.create(
    organization=org,
    name='Consulta de Afiliación',
    description='Explica el proceso de afiliación para trabajadores y empleadores, verificación y actualización de datos.',
    nodes=flow7_nodes,
    edges=flow7_edges,
    trigger='consulta_afiliacion',
    channel='web',
    is_active=True,
)


# ─── FLOW 8: EDUCACIÓN Y FORMACIÓN ────────────────────────────────────────────

flow8_nodes = [
    node('n1', 'start'),
    node('n2', 'message', text=(
        'Comfaguajira tiene una amplia oferta educativa y de formacion para afiliados y sus familias. '
        'Aqui te cuento los servicios disponibles:'
    )),
    node('n3', 'quickReply',
        text='Que servicio educativo te interesa?',
        options=[
            'Becas y subsidios educativos',
            'Capacitaciones y cursos',
            'Educacion inicial FONINEZ',
            'Credito educativo',
        ],
        variable='edu_opcion',
    ),
    node('n4', 'condition',
        variable='edu_opcion',
        operator='eq',
        value='Becas y subsidios educativos',
    ),
    node('n5', 'message', text=(
        'Subsidio Educativo Comfaguajira:\n\n'
        'Los trabajadores afiliados reciben subsidio en especie en educacion:\n'
        '- Cupo escolar en colegios vinculados\n'
        '- Apoyo para matricula y utiles\n'
        '- Subsidio para estudios superiores\n\n'
        'El valor depende de tu categoria salarial (A, B o C).\n'
        'Para inscribir beneficiarios, acercate a la sede con el certificado de matricula.'
    )),
    node('n6', 'condition',
        variable='edu_opcion',
        operator='eq',
        value='Capacitaciones y cursos',
    ),
    node('n7', 'message', text=(
        'Programas de Capacitacion Comfaguajira:\n\n'
        'Ofrecemos cursos y talleres en:\n'
        '- Tecnologia e informatica\n'
        '- Emprendimiento y negocios\n'
        '- Idiomas\n'
        '- Oficios tecnicos\n'
        '- Salud y bienestar\n\n'
        'La mayoria son gratuitos o a bajo costo para afiliados.\n'
        'Consulta el calendario en comfaguajira.com.co o en cualquier sede.'
    )),
    node('n8', 'condition',
        variable='edu_opcion',
        operator='eq',
        value='Educacion inicial FONINEZ',
    ),
    node('n9', 'message', text=(
        'FONINEZ - Atencion a la Primera Infancia:\n\n'
        'Jardines infantiles para hijos de trabajadores afiliados:\n'
        '- Atencion a ninos de 0 a 5 anos\n'
        '- Educacion inicial con enfoque cultural y nutricional\n'
        '- Cupos subsidiados para categorias A y B\n'
        '- Horario: lunes a viernes 7am-5pm\n\n'
        'Para inscripcion, presenta el registro civil del menor y certificado de afiliacion.'
    )),
    node('n10', 'message', text=(
        'Credito Educativo Comfaguajira:\n\n'
        '- Montos desde $500.000 hasta $15.000.000\n'
        '- Plazo hasta 24 meses con tasa preferencial\n'
        '- Para: matricula, semestre universitario, cursos tecnicos, posgrados\n\n'
        'Requisitos: afiliado activo, cedula vigente, recibo de matricula.\n'
        'Solicita en cualquier sede o escribe "credito" para mas informacion.'
    )),
    node('n11', 'message', text=(
        'Para mas informacion visita comfaguajira.com.co o acercate a cualquier sede. '
        'Escribe "asesor" si prefieres hablar con una persona.'
    )),
    node('n12', 'end', message=''),
    meta_node('keyword',
        keywords=[
            'educacion', 'educacion inicial', 'beca', 'becas', 'colegio',
            'servicios de educacion', 'capacitacion', 'cursos', 'talleres',
            'formacion', 'foninez', 'jardin infantil', 'subsidio educativo',
            'credito educativo', 'que estudios', 'estudiar', 'clases',
        ],
        canales=['web', 'app'],
    ),
]

flow8_edges = [
    edge('e1', 'n1', 'n2'),
    edge('e2', 'n2', 'n3'),
    edge('e3', 'n3', 'n4'),
    edge('e4', 'n4', 'n5', condition='yes'),
    edge('e5', 'n4', 'n6', condition='no'),
    edge('e6', 'n6', 'n7', condition='yes'),
    edge('e7', 'n6', 'n8', condition='no'),
    edge('e8', 'n8', 'n9', condition='yes'),
    edge('e9', 'n8', 'n10', condition='no'),
    edge('e10', 'n3', 'n10', condition='option:Credito educativo'),
    edge('e11', 'n5', 'n11'),
    edge('e12', 'n7', 'n11'),
    edge('e13', 'n9', 'n11'),
    edge('e14', 'n10', 'n11'),
    edge('e15', 'n11', 'n12'),
]

Flow.objects.create(
    organization=org,
    name='Educacion y Formacion',
    description='Informacion sobre becas, subsidio educativo, FONINEZ, capacitaciones y credito educativo.',
    nodes=flow8_nodes,
    edges=flow8_edges,
    trigger='consulta_educacion',
    channel='web',
    is_active=True,
)

# ─── SUMMARY ──────────────────────────────────────────────────────────────────

total_flows = Flow.objects.filter(organization=org).count()
total_intents = CustomIntent.objects.filter(organization=org).count()

print(f'\n✅ Done!')
print(f'   Flows created:   {total_flows}')
print(f'   Intents created: {total_intents}')
print()
print('Flows:')
for f in Flow.objects.filter(organization=org).order_by('name'):
    print(f'  [{f.trigger:30s}] {f.name}')
print()
print('Intents:')
for i in CustomIntent.objects.filter(organization=org).order_by('label'):
    print(f'  {i.name:35s} — {i.label}')
