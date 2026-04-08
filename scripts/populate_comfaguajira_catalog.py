"""
Populates Comfaguajira product catalog with real 2026 services and price variants.
Run:  .venv/Scripts/python.exe scripts/populate_comfaguajira_catalog.py

Replaces the 7 generic seed products with structured service offerings.
Each product has variants: Cat A / Cat B / Cat C / Empresa Afiliada / Particular.
"""
import django, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.ecommerce.models import Product, ProductVariant
from apps.accounts.models import Organization

ORG_ID = 'd620ebfb-71b3-48f6-ab9e-1f187f93d9fb'
org = Organization.objects.get(id=ORG_ID)
print(f'Org: {org.name}')

# Wipe existing products
deleted, _ = Product.objects.filter(organization=org).delete()
print(f'Deleted {deleted} existing products.')

# ── Helpers ───────────────────────────────────────────────────────────────────
def svc(title, category, description, variants,
        price_type='fixed', requires_booking=True,
        fulfillment_notes='', attributes=None, tags=None):
    """Create a service Product with ProductVariant rows."""
    p = Product.objects.create(
        organization=org,
        title=title,
        category=category,
        description=description,
        offer_type='service',
        price_type=price_type,
        service_mode='onsite',
        requires_booking=requires_booking,
        requires_shipping=False,
        fulfillment_notes=fulfillment_notes,
        attributes=attributes or {},
        tags=tags or [],
        status='active',
        is_active=True,
    )
    for v in variants:
        ProductVariant.objects.create(
            product=p,
            sku=v.get('sku', ''),
            name=v['name'],
            price=v['price'],
            cost=0,
            stock=0,
            reserved=0,
            metadata=v.get('meta', {}),
        )
    print(f'  [+] {title} ({len(variants)} variantes)')
    return p

CATS = [
    ('Cat A', 'cat-a'),
    ('Cat B', 'cat-b'),
    ('Cat C', 'cat-c'),
    ('Empresa Afiliada', 'emp'),
    ('Particular', 'particular'),
]

def variants(prices, slug):
    """Build 5 variant dicts from a (A, B, C, Emp, Part) tuple and a slug prefix."""
    result = []
    labels = ['Cat A', 'Cat B', 'Cat C', 'Empresa Afiliada', 'Particular']
    slugs  = ['cat-a', 'cat-b', 'cat-c', 'emp', 'particular']
    for label, sk, price in zip(labels, slugs, prices):
        result.append({'name': label, 'sku': f'{slug}-{sk}', 'price': price})
    return result

def v2(a, b, slug):
    """Only Cat A and Cat B (promotional / subsidized services)."""
    return [
        {'name': 'Cat A', 'sku': f'{slug}-cat-a', 'price': a},
        {'name': 'Cat B', 'sku': f'{slug}-cat-b', 'price': b},
    ]

# ── RECREACIÓN — ANAS MAI ─────────────────────────────────────────────────────
print('\n— RECREACIÓN ANAS MAI —')

svc('Entrada y piscina adulto — Anas Mai',
    category='Recreacion - Anas Mai',
    description='Acceso al Centro Socio Cultural y Recreativo Anas Mai con derecho a piscinas. '
                'Horario: martes a viernes 9am–3pm, sábado/domingo/festivos 9am–5pm. '
                'Obligatorio vestido de baño reglamentario.',
    variants=variants((3800, 6500, 13000, 14100, 19500), 'anas-mai-entrada'),
    requires_booking=False,
    tags=['recreacion', 'anas-mai', 'piscina'])

svc('Pasadía Anas Mai sin transporte (comida + entrada)',
    category='Recreacion - Anas Mai',
    description='Almuerzo tipo asado + entrada al centro con derecho a piscinas. '
                'No incluye canchas deportivas. Servicio sujeto a disponibilidad.',
    variants=variants((38400, 41000, 48000, 49000, 54000), 'pasadia-anas-mai-st'),
    requires_booking=True,
    tags=['recreacion', 'anas-mai', 'pasadia'])

svc('Pasadía Anas Mai desde Maicao (con transporte)',
    category='Recreacion - Anas Mai',
    description='Transporte Maicao–Anas Mai–Maicao + almuerzo tipo asado + entrada con piscinas. '
                'Requiere reservación previa. Presentarse 30 min antes.',
    variants=variants((56000, 62000, 97000, 102000, 111000), 'pasadia-anas-mai-maicao'),
    requires_booking=True,
    tags=['recreacion', 'anas-mai', 'pasadia', 'transporte'])

svc('Pasadía Anas Mai desde Manaure / Uribia (con transporte)',
    category='Recreacion - Anas Mai',
    description='Transporte Manaure/Uribia–Anas Mai–ida y vuelta + almuerzo + entrada con piscinas.',
    variants=variants((60000, 67000, 100000, 106000, 115000), 'pasadia-anas-mai-manaure'),
    requires_booking=True,
    tags=['recreacion', 'anas-mai', 'pasadia', 'transporte'])

svc('Pasadía Anas Mai desde Fonseca / Barrancas (con transporte)',
    category='Recreacion - Anas Mai',
    description='Transporte Fonseca/Barrancas–Anas Mai–ida y vuelta + almuerzo + entrada con piscinas.',
    variants=variants((59000, 66000, 104000, 110000, 125000), 'pasadia-anas-mai-fonseca'),
    requires_booking=True,
    tags=['recreacion', 'anas-mai', 'pasadia', 'transporte'])

svc('Pasadía Anas Mai desde San Juan / Villanueva / El Molino (con transporte)',
    category='Recreacion - Anas Mai',
    description='Transporte San Juan/Villanueva/El Molino–Anas Mai–ida y vuelta + almuerzo + entrada con piscinas.',
    variants=variants((71000, 84000, 124000, 133000, 143000), 'pasadia-anas-mai-sanjuan'),
    requires_booking=True,
    tags=['recreacion', 'anas-mai', 'pasadia', 'transporte'])

# Alquiler espacios Anas Mai
svc('Alquiler Auditorio Anas Mai (4 horas)',
    category='Alquiler de Espacios - Anas Mai',
    description='Auditorio Centro Socio Cultural Anas Mai por 4 horas. Incluye: video beam, '
                'agua, café, aromática, sillas, planta eléctrica, wifi básico, AC, vigilancia.',
    variants=variants((478400, 549000, 866000, 996000, 1127000), 'anas-mai-aud-4h'),
    tags=['alquiler', 'anas-mai', 'eventos'])

svc('Alquiler Auditorio Anas Mai (8 horas)',
    category='Alquiler de Espacios - Anas Mai',
    description='Auditorio Centro Socio Cultural Anas Mai por 8 horas. Incluye: video beam, '
                'agua, café, aromática, sillas, planta eléctrica, wifi básico, AC, vigilancia.',
    variants=variants((957000, 1099000, 1732000, 1991000, 2255000), 'anas-mai-aud-8h'),
    tags=['alquiler', 'anas-mai', 'eventos'])

svc('Alquiler Salón N.º 6 Anas Mai 100% (8 horas)',
    category='Alquiler de Espacios - Anas Mai',
    description='Salón N.º 6 a capacidad completa, Centro Anas Mai, 8 horas. '
                'El mayor salón del centro. Incluye mismo paquete que el auditorio.',
    variants=variants((1268000, 1488000, 2070000, 2329000, 2588000), 'anas-mai-s6-8h'),
    tags=['alquiler', 'anas-mai', 'eventos'])

# ── RECREACIÓN — MAZIRUMA ─────────────────────────────────────────────────────
print('\n— RECREACIÓN MAZIRUMA —')

svc('Entrada al centro — Maziruma (Dibulla)',
    category='Recreacion - Maziruma',
    description='Acceso al Centro Recreacional y Vacacional Maziruma en Dibulla. '
                'Incluye piscinas, parque infantil, canchas deportivas y parqueadero vigilado. '
                'Horario pasadía: martes, domingos y festivos 9am–6pm.',
    variants=variants((650, 3250, 11900, 13000, 18000), 'maziruma-entrada'),
    requires_booking=False,
    tags=['recreacion', 'maziruma', 'piscina'])

svc('Pasadía Maziruma sin transporte (comida + entrada)',
    category='Recreacion - Maziruma',
    description='Almuerzo ejecutivo + entrada al centro con piscinas. Maziruma, Dibulla.',
    variants=variants((36650, 39250, 48000, 49000, 54300), 'pasadia-maziruma-st'),
    requires_booking=True,
    tags=['recreacion', 'maziruma', 'pasadia'])

svc('Pasadía Maziruma desde Riohacha (con transporte)',
    category='Recreacion - Maziruma',
    description='Transporte Riohacha–Maziruma–Riohacha + almuerzo + entrada con piscinas.',
    variants=variants((55200, 62600, 89100, 94400, 101800), 'pasadia-maziruma-riohacha'),
    requires_booking=True,
    tags=['recreacion', 'maziruma', 'pasadia', 'transporte'])

svc('Pasadía Maziruma desde Maicao (con transporte)',
    category='Recreacion - Maziruma',
    description='Transporte Maicao–Maziruma–Maicao + almuerzo + entrada con piscinas.',
    variants=variants((67300, 76900, 136600, 146200, 155800), 'pasadia-maziruma-maicao'),
    requires_booking=True,
    tags=['recreacion', 'maziruma', 'pasadia', 'transporte'])

# Alojamiento Maziruma — selección de planes más populares
svc('Alojamiento Maziruma — Cabaña Plan Continental (por persona/noche)',
    category='Alojamiento - Maziruma',
    description='1 noche en cabaña con AC + desayuno americano. Temporada alta. '
                'Check-in 3pm, check-out 12m. Niños < 5 años no pagan (solo seguro hotelero).',
    variants=variants((62100, 70400, 128700, 142700, 161700), 'maziruma-cab-cont-triple'),
    requires_booking=True,
    fulfillment_notes='Aplica para acomodación triple. Cuádruple y quíntuple tienen precio menor.',
    tags=['alojamiento', 'maziruma', 'cabaña'])

svc('Alojamiento Maziruma — Cabaña Plan Americano Modificado (por persona/noche)',
    category='Alojamiento - Maziruma',
    description='1 noche en cabaña con AC + desayuno + almuerzo. Temporada alta. '
                'Acomodación triple. Check-in 3pm, check-out 12m.',
    variants=variants((98100, 106400, 164700, 178700, 197700), 'maziruma-cab-am-mod-triple'),
    requires_booking=True,
    tags=['alojamiento', 'maziruma', 'cabaña'])

svc('Alojamiento Maziruma — Cabaña Plan Americano (por persona/noche)',
    category='Alojamiento - Maziruma',
    description='1 noche en cabaña con AC + desayuno + almuerzo + cena. Temporada alta. '
                'Acomodación triple. Check-in 3pm, check-out 12m.',
    variants=variants((121600, 129900, 188200, 202200, 221200), 'maziruma-cab-am-triple'),
    requires_booking=True,
    tags=['alojamiento', 'maziruma', 'cabaña'])

svc('Alojamiento Maziruma — Habitación tipo hotel Plan Continental (por persona/noche)',
    category='Alojamiento - Maziruma',
    description='1 noche en habitación tipo hotel con AC + desayuno americano. '
                'Temporada alta. Habitación sencilla. Check-in 3pm, check-out 12m.',
    variants=variants((99700, 109700, 199100, 216700, 241700), 'maziruma-hotel-cont-senc'),
    requires_booking=True,
    fulfillment_notes='Precio para habitación sencilla. Doble/triple/cuádruple tienen precio menor por persona.',
    tags=['alojamiento', 'maziruma', 'hotel'])

svc('Alojamiento Maziruma — Apartamento Plan Continental (por persona/noche)',
    category='Alojamiento - Maziruma',
    description='1 noche en apartamento con AC + desayuno americano. Temporada alta. '
                'Acomodación cuádruple. Check-in 3pm, check-out 12m.',
    variants=variants((61700, 70500, 116500, 145000, 163000), 'maziruma-apto-cont-cuad'),
    requires_booking=True,
    tags=['alojamiento', 'maziruma', 'apartamento'])

svc('Alojamiento Maziruma — Glamping Kogui Plan Continental (por persona/noche)',
    category='Alojamiento - Maziruma',
    description='1 noche en Glamping Kogui con AC + desayuno americano. Temporada alta. '
                'Acomodación doble. Check-in 3pm, check-out 12m.',
    variants=variants((42500, 49500, 92500, 119500, 136500), 'maziruma-glamping-kogui-cont'),
    requires_booking=True,
    tags=['alojamiento', 'maziruma', 'glamping'])

# ── RECREACIÓN — POLIDEPORTIVO HATONUEVO ─────────────────────────────────────
print('\n— POLIDEPORTIVO HATONUEVO —')

svc('Entrada al Polideportivo Hatonuevo',
    category='Recreacion - Hatonuevo',
    description='Acceso al Polideportivo de Hatonuevo: piscinas, parque infantil, '
                'canchas deportivas y parqueadero vigilado.',
    variants=variants((300, 1300, 4700, 5200, 7400), 'hatonuevo-entrada'),
    requires_booking=False,
    tags=['recreacion', 'hatonuevo'])

svc('Pasadía Polideportivo Hatonuevo sin transporte (comida + entrada)',
    category='Recreacion - Hatonuevo',
    description='Almuerzo ejecutivo + entrada con piscinas. Hatonuevo.',
    variants=variants((25600, 30200, 40800, 41300, 43500), 'pasadia-hatonuevo-st'),
    requires_booking=True,
    tags=['recreacion', 'hatonuevo', 'pasadia'])

svc('Pasadía Polideportivo Hatonuevo desde Riohacha (con transporte)',
    category='Recreacion - Hatonuevo',
    description='Transporte Riohacha–Hatonuevo–Riohacha + almuerzo + entrada.',
    variants=variants((62800, 71200, 101400, 107000, 116000), 'pasadia-hatonuevo-riohacha'),
    requires_booking=True,
    tags=['recreacion', 'hatonuevo', 'transporte'])

# ── TURISMO SOCIAL ────────────────────────────────────────────────────────────
print('\n— TURISMO SOCIAL —')

svc('Tour Cabo de la Vela — 1 día (4 personas, desde Riohacha)',
    category='Turismo Social',
    description='Pasadía a Cabo de la Vela. Incluye: acompañamiento, caminata al Faro, '
                'Pilón de Azúcar, Salinas de Manaure, 1 almuerzo con pescado, '
                'transporte Riohacha–Cabo–Riohacha en camioneta, seguro de viaje. '
                'Salida 5:00am, regreso ~3:00pm. Mín. 4 personas.',
    variants=variants((145000, 173000, 289000, 305000, 314600), 'cabo-1d-4pax-riohacha'),
    requires_booking=True,
    tags=['turismo', 'cabo-de-la-vela'])

svc('Tour Cabo de la Vela — 1 día (grupos 20+ personas, desde Riohacha)',
    category='Turismo Social',
    description='Pasadía grupal a Cabo de la Vela. Incluye: Faro, Pilón de Azúcar, '
                'Salinas de Manaure, almuerzo con pescado, transporte en bus, seguro de viaje. '
                'Salida 5:30am, regreso ~3:00pm. Mín. 20 personas.',
    variants=variants((157000, 188000, 314000, 334000, 357000), 'cabo-1d-20pax-riohacha'),
    requires_booking=True,
    tags=['turismo', 'cabo-de-la-vela', 'grupos'])

svc('Tour Cabo de la Vela — 2 días / 1 noche (4 personas)',
    category='Turismo Social',
    description='Cabo de la Vela 2D/1N en camioneta desde Riohacha. Incluye: Faro, Pilón de Azúcar, '
                'Salinas, 2 almuerzos, 1 cena, 1 desayuno, transporte y 1 noche en cabaña wayuu '
                '(cama, abanico, baño privado — sin toallas ni artículos de aseo). Mín. 4 personas.',
    variants=variants((341000, 409000, 681800, 701000, 716800), 'cabo-2d-4pax'),
    requires_booking=True,
    tags=['turismo', 'cabo-de-la-vela', 'alojamiento'])

svc('Tarde de Ranchería Wayuu — con transporte (4 personas)',
    category='Turismo Social',
    description='Visita a Ranchería Iwouya (km 17 vía Valledupar). Incluye: cóctel de Chirrinchi, '
                'charla sobre mitos y leyendas wayuu, plato típico Friche, baile Ionna/Chichamaya, '
                'transporte Riohacha–Ranchería–Riohacha en camioneta, seguro de viaje. '
                'Salida 3pm, regreso 5pm.',
    variants=variants((271000, 325000, 542300, 595000, 625000), 'rancheria-4pax'),
    requires_booking=True,
    tags=['turismo', 'rancheria', 'cultura-wayuu'])

svc('Tarde de Ranchería Wayuu — con transporte (grupos 20+)',
    category='Turismo Social',
    description='Visita grupal en buseta a Ranchería Wayuu. Incluye: Chirrinchi, Friche, '
                'Ionna/Chichamaya, guía y seguro de viaje. Salida 3pm, regreso 5pm.',
    variants=variants((51000, 65000, 144000, 150000, 159200), 'rancheria-20pax'),
    requires_booking=True,
    tags=['turismo', 'rancheria', 'cultura-wayuu', 'grupos'])

svc('Santuario Flora y Fauna Los Flamencos — 4 personas (desde Riohacha)',
    category='Turismo Social',
    description='Camarones, ~20 min de Riohacha. Caminata a la laguna, recorrido en canoa artesanal '
                '(~2 h), avistamiento de flamencos rosados (aves migratorias, no garantizadas). '
                'Incluye: transporte, 1 almuerzo con pescado, paseo en canoa, seguro de viaje.',
    variants=variants((64000, 82000, 183200, 205000, 226500), 'flora-fauna-4pax'),
    requires_booking=True,
    tags=['turismo', 'flamencos', 'naturaleza'])

svc('Tour Tierra Guajira — 5 días / 4 noches (grupos 20+, con transporte)',
    category='Turismo Social',
    description='Paquete completo de La Guajira para grupos. Incluye: hotel Riohacha, '
                'alimentación completa, City Tour, Flamencos Rosados, Salinas Manaure, '
                'Cabo de la Vela, Tarde de Ranchería, transfers, guía y seguros. '
                'No incluye tiquetes aéreos.',
    price_type='quote_required',
    variants=[
        {'name': 'Empresa Afiliada', 'sku': 'tierra-guajira-emp', 'price': 2000000},
        {'name': 'Particular', 'sku': 'tierra-guajira-part', 'price': 1932400},
    ],
    requires_booking=True,
    tags=['turismo', 'tierra-guajira', 'paquete'])

svc('Tour Alta Guajira — 4 noches (grupos 20+)',
    category='Turismo Social',
    description='4N: 2 en Riohacha, 1 en Cabo de la Vela, 1 en Punta Gallinas. '
                'Recorridos: Salinas, Faro, Pilón de Azúcar, Dunas de Taroa, Bahía Honda, '
                'Portete. Tarde de Ranchería, avistamiento de aves. Transfer aeropuerto, '
                'traslados en camionetas, seguros de viaje.',
    price_type='quote_required',
    variants=[
        {'name': 'Empresa Afiliada', 'sku': 'alta-guajira-emp', 'price': 1137000},
        {'name': 'Particular', 'sku': 'alta-guajira-part', 'price': 1180200},
    ],
    requires_booking=True,
    tags=['turismo', 'alta-guajira', 'paquete'])

svc('Pasadía Palomino con transporte (grupos 20+)',
    category='Turismo Social',
    description='Bus Riohacha–Palomino–Riohacha + acompañamiento + almuerzo ejecutivo '
                '+ seguro médico. Salida 7am, llegada 4pm. Niños desde 3 años pagan.',
    variants=variants((72000, 87000, 144500, 163000, 178100), 'palomino-ct-20pax'),
    requires_booking=True,
    tags=['turismo', 'palomino'])

svc('Plan Vuelve a Mayapo — por persona',
    category='Turismo Social',
    description='Visita a Mayapo (~30 min de Riohacha). Incluye: michelada de bienvenida, '
                'almuerzo con bebida, disfrute de instalaciones.',
    variants=variants((64000, 76000, 127000, 144000, 149800), 'mayapo-persona'),
    requires_booking=True,
    tags=['turismo', 'mayapo', 'playa'])

# ── EDUCACIÓN ─────────────────────────────────────────────────────────────────
print('\n— EDUCACIÓN —')

svc('Taller educación informal 4 horas',
    category='Educacion Informal',
    description='Taller temático de 4 horas (responsabilidad laboral, comunicación asertiva, '
                'liderazgo, inteligencia emocional, trabajo en equipo, entre otras). '
                'Incluye: honorarios docente y salón. Capacidad máx. 25 pax.',
    variants=variants((25200, 30500, 39800, 45200, 51600), 'taller-4h'),
    requires_booking=True,
    tags=['educacion', 'taller'])

svc('Seminario educación informal 8 horas',
    category='Educacion Informal',
    description='Seminario de 8 horas. Mismas temáticas que talleres + mayor profundidad. '
                'Incluye: honorarios docente y salón. Capacidad máx. 25 pax.',
    variants=variants((41300, 46700, 64100, 73800, 78200), 'seminario-8h'),
    requires_booking=True,
    tags=['educacion', 'seminario'])

svc('Seminario educación informal 10 horas',
    category='Educacion Informal',
    description='Seminario completo de 10 horas. Incluye: honorarios docente y salón.',
    variants=variants((50700, 57400, 79300, 91200, 97400), 'seminario-10h'),
    requires_booking=True,
    tags=['educacion', 'seminario'])

svc('Curso educación informal 20 horas',
    category='Educacion Informal',
    description='Curso de 20 horas. Incluye refrigerio. Temáticas: Wayuunaiki básico, '
                'marketing digital, servicio al cliente, Excel, informática básica, entre otras.',
    variants=variants((98800, 113400, 154400, 176400, 193700), 'curso-20h'),
    requires_booking=True,
    tags=['educacion', 'curso'])

svc('Curso educación informal 40 horas',
    category='Educacion Informal',
    description='Curso de 40 horas. Incluye refrigerio y material.',
    variants=variants((180600, 207900, 285300, 326500, 355800), 'curso-40h'),
    requires_booking=True,
    tags=['educacion', 'curso'])

svc('Diplomado especializado 80 horas',
    category='Educacion Informal',
    description='Diplomado de 80 horas presencial. Incluye material educativo digital. '
                'Temáticas: docencia universitaria, gestión financiera, negocios digitales, '
                'habilidades comerciales, entre otras. Capacidad máx. 30 pax.',
    variants=variants((586500, 671800, 920200, 1059200, 1154000), 'diplomado-80h'),
    requires_booking=True,
    tags=['educacion', 'diplomado'])

svc('Diplomado especializado 120 horas',
    category='Educacion Informal',
    description='Diplomado de 120 horas presencial con material digital. Capacidad máx. 30 pax.',
    variants=variants((862000, 987000, 1357500, 1561200, 1702000), 'diplomado-120h'),
    requires_booking=True,
    tags=['educacion', 'diplomado'])

svc('Formación Laboral — semestre Técnico Laboral (por semestre)',
    category='Formacion Laboral',
    description='Programas técnicos laborales de 600 a 1.200 horas (hasta 4 semestres). '
                'Pago semestral. Modalidad presencial.',
    variants=variants((182400, 369100, 675200, 706000, 759900), 'tecnico-semestre'),
    requires_booking=True,
    tags=['educacion', 'tecnico-laboral'])

svc('Escuela de Artes — Pintura nivel 1 (32 horas)',
    category='Cultura - Escuela de Artes',
    description='Curso de pintura nivel 1: lápiz. 32 horas académicas. '
                'Jornada diurna, nocturna o sabatina. Desde 7 años.',
    variants=variants((48600, 55000, 207400, 307000, 337000), 'artes-pintura-1'),
    requires_booking=True,
    tags=['cultura', 'artes', 'pintura'])

svc('Escuela de Artes — Música nivel 1: Flauta y/o Guitarra (32 horas)',
    category='Cultura - Escuela de Artes',
    description='Curso de música nivel 1: flauta y/o guitarra. 32 horas. Desde 7 años.',
    variants=variants((61000, 69000, 110200, 149000, 259200), 'artes-musica-1'),
    requires_booking=True,
    tags=['cultura', 'artes', 'musica'])

svc('Escuela de Artes — Danza (32 horas)',
    category='Cultura - Escuela de Artes',
    description='Curso de danza. 32 horas académicas. Jornada diurna, nocturna o sabatina.',
    variants=variants((63000, 71300, 266000, 393200, 423400), 'artes-danza'),
    requires_booking=True,
    tags=['cultura', 'artes', 'danza'])

svc('Escuela de Artes — Teatro (32 horas)',
    category='Cultura - Escuela de Artes',
    description='Curso de teatro. 32 horas académicas.',
    variants=variants((58400, 66000, 246300, 363000, 397500), 'artes-teatro'),
    requires_booking=True,
    tags=['cultura', 'artes', 'teatro'])

# ── SALUD IPS ─────────────────────────────────────────────────────────────────
print('\n— SALUD IPS —')

svc('Consulta Medicina General — IPS Comfaguajira',
    category='Salud IPS',
    description='Consulta médica general (primera vez o control/seguimiento). '
                'Tarifa particular única para todas las categorías.',
    price_type='fixed',
    variants=[
        {'name': 'Primera vez o control', 'sku': 'ips-med-gral', 'price': 29800},
    ],
    requires_booking=True,
    tags=['salud', 'consulta', 'medicina-general'])

svc('Consulta Especialista — IPS Comfaguajira',
    category='Salud IPS',
    description='Consulta con especialista. Tarifa estándar por especialidad. '
                'Especialidades disponibles: Cardiología, Dermatología, Ginecología, '
                'Medicina Interna, Ortopedia, Otorrinolaringología, Pediatría, Urología y otras.',
    price_type='variable',
    variants=[
        {'name': 'Especialista médico (general)', 'sku': 'ips-esp-medico', 'price': 96200},
        {'name': 'Especialista odontológico / Fonoaudiología / Nutrición', 'sku': 'ips-esp-otro', 'price': 56400},
        {'name': 'Psiquiatría', 'sku': 'ips-psiquiatria', 'price': 144800},
        {'name': 'Psicología', 'sku': 'ips-psicologia', 'price': 57500},
    ],
    requires_booking=True,
    tags=['salud', 'consulta', 'especialista'])

svc('Programa Nutrición — Consulta Crecer Sano',
    category='Salud IPS',
    description='Consulta de nutrición del Programa Crecer Sano. Dirigida a niños de '
                '6 meses a 14 años. Categorías A y B reciben subsidio del 63%.',
    price_type='variable',
    variants=[
        {'name': 'Cat A y B (con subsidio 63%)', 'sku': 'crecer-sano-ab', 'price': 13000},
        {'name': 'Tarifa plena (Cat C / Particular)', 'sku': 'crecer-sano-plena', 'price': 35324},
    ],
    requires_booking=True,
    tags=['salud', 'nutricion', 'crecer-sano'])

# ── DEPORTES Y GIMNASIO ───────────────────────────────────────────────────────
print('\n— DEPORTES Y GIMNASIO —')

svc('Gimnasio Comfaguajira — mensualidad',
    category='Deportes - Gimnasio',
    description='Mensualidad del gimnasio en Centro Anas Mai. Horario completo. '
                'Descuentos disponibles por semestre (30%), trimestre (20%) y anualidad.',
    variants=variants((30000, 38000, 66000, 75000, 80000), 'gimnasio-mensual'),
    requires_booking=False,
    tags=['deportes', 'gimnasio'])

svc('Escuela Deportiva — Natación Infantil (mensualidad)',
    category='Deportes - Escuelas',
    description='Mensualidad escuela de natación para niños de 8 a 11 años. '
                'Inscripción/póliza única adicional: $38.000.',
    variants=variants((46000, 61000, 96000, 94000, 103000), 'escuela-natacion-infantil'),
    requires_booking=True,
    tags=['deportes', 'natacion', 'escuelas'])

svc('Escuela Deportiva — Fútbol (mensualidad)',
    category='Deportes - Escuelas',
    description='Mensualidad escuela de fútbol. Inscripción/póliza única adicional: $38.000.',
    variants=variants((33000, 44000, 75000, 75000, 82000), 'escuela-futbol'),
    requires_booking=True,
    tags=['deportes', 'futbol', 'escuelas'])

svc('Torneo Fútbol 7 (por equipo)',
    category='Deportes - Torneos',
    description='Torneo de fútbol 7 disponible en Riohacha, Maicao y San Juan del Cesar. '
                'Incluye: inscripción, hidratación, juzgamiento, inflables deportivos (solo Riohacha).',
    variants=variants((674000, 842000, 1123200, 1303000, 1337000), 'torneo-futbol7'),
    requires_booking=True,
    tags=['deportes', 'futbol7', 'torneo'])

svc('Alquiler cancha sintética Anas Mai (1 hora)',
    category='Deportes - Cancha',
    description='Alquiler de cancha sintética en Anas Mai. '
                'Horario diurno: 6am–6pm. Horario nocturno: 6pm–11pm.',
    price_type='variable',
    variants=[
        {'name': 'Cat A — Diurno', 'sku': 'cancha-a-d', 'price': 42000},
        {'name': 'Cat B — Diurno', 'sku': 'cancha-b-d', 'price': 49000},
        {'name': 'Cat C — Diurno', 'sku': 'cancha-c-d', 'price': 69200},
        {'name': 'Empresa Afil. — Diurno', 'sku': 'cancha-emp-d', 'price': 80000},
        {'name': 'Particular — Diurno', 'sku': 'cancha-part-d', 'price': 86000},
        {'name': 'Cat A — Nocturno', 'sku': 'cancha-a-n', 'price': 51000},
        {'name': 'Cat B — Nocturno', 'sku': 'cancha-b-n', 'price': 57000},
        {'name': 'Cat C — Nocturno', 'sku': 'cancha-c-n', 'price': 78000},
        {'name': 'Empresa Afil. — Nocturno', 'sku': 'cancha-emp-n', 'price': 89000},
        {'name': 'Particular — Nocturno', 'sku': 'cancha-part-n', 'price': 96000},
    ],
    requires_booking=True,
    tags=['deportes', 'cancha', 'futbol'])

# ── PROGRAMAS SOCIALES ────────────────────────────────────────────────────────
print('\n— PROGRAMAS SOCIALES —')

svc('Programa Adulto Mayor — mensualidad (permanente)',
    category='Programas Sociales',
    description='Mensualidad del programa Adulto Mayor "La Edad de Trigo" en Riohacha. '
                'Incluye: actividades de salud física, educación y recreación. '
                '100% subsidiado para Cat A y B en modalidad itinerante.',
    price_type='variable',
    variants=[
        {'name': 'Cat A (permanente)', 'sku': 'adulto-mayor-a', 'price': 5900},
        {'name': 'Cat B (permanente)', 'sku': 'adulto-mayor-b', 'price': 11800},
        {'name': 'Cat C (permanente)', 'sku': 'adulto-mayor-c', 'price': 60700},
        {'name': 'Cat D (permanente)', 'sku': 'adulto-mayor-d', 'price': 65400},
        {'name': 'Cat A y B (itinerante)', 'sku': 'adulto-mayor-itin-ab', 'price': 0},
        {'name': 'Cat C (itinerante)', 'sku': 'adulto-mayor-itin-c', 'price': 45300},
    ],
    requires_booking=True,
    tags=['social', 'adulto-mayor'])

# ── CRÉDITO SOCIAL ────────────────────────────────────────────────────────────
print('\n— CRÉDITO SOCIAL —')

svc('Crédito Social Comfaguajira',
    category='Credito Social',
    description='Crédito personal para afiliados activos. Líneas disponibles: Salud, Recreación, '
                'Turismo, Educación, Libre Inversión y Compra de Cartera. '
                'Tasas: Cat A 1.4%, Cat B 1.5%, Cat C 1.6% mensual. '
                'Plazo máximo: hasta 60 cuotas. Estudio de crédito: $20.000. '
                'Descuento por nómina (libranza).',
    price_type='quote_required',
    requires_booking=False,
    variants=[
        {'name': 'Cat A — Libre Inversión (tasa 1.4% m.v.)', 'sku': 'credito-a-libre', 'price': 0},
        {'name': 'Cat B — Libre Inversión (tasa 1.5% m.v.)', 'sku': 'credito-b-libre', 'price': 0},
        {'name': 'Cat C — Libre Inversión (tasa 1.6% m.v.)', 'sku': 'credito-c-libre', 'price': 0},
        {'name': 'Compra de cartera — Cat A/B (tasa 1.3–1.4% m.v.)', 'sku': 'credito-cartera', 'price': 0},
    ],
    tags=['credito', 'financiero'])

# ── ALQUILER ESPACIOS EDUCATIVOS ──────────────────────────────────────────────
print('\n— ALQUILER ESPACIOS —')

svc('Alquiler Auditorio Centro Educativo (4 horas)',
    category='Alquiler de Espacios - Educativo',
    description='Auditorio del Centro de Desarrollo Educativo Comfaguajira por 4 horas. '
                'Incluye: sillas acolchadas, AC, tablero acrílico, 2 marcadores, vigilancia e IVA.',
    variants=variants((274000, 294000, 355000, 416000, 441000), 'edu-auditorio-4h'),
    requires_booking=True,
    tags=['alquiler', 'educacion', 'auditorio'])

svc('Teatro Akuaipaa — 4 horas diurno (educativo)',
    category='Alquiler de Espacios - Teatro',
    description='Teatro Akuaipaa por 4 horas en horario diurno, uso educativo. '
                'Incluye tiempo de montaje y desmontaje. 50% de anticipo obligatorio.',
    price_type='fixed',
    variants=[
        {'name': 'Uso educativo — diurno 4h', 'sku': 'teatro-edu-4h-d', 'price': 1057400},
        {'name': 'Uso cultural — diurno 4h', 'sku': 'teatro-cult-4h-d', 'price': 1322000},
        {'name': 'Uso empresarial — diurno 4h', 'sku': 'teatro-emp-4h-d', 'price': 1375000},
        {'name': 'Uso comercial — diurno 4h', 'sku': 'teatro-com-4h-d', 'price': 1587000},
        {'name': 'Uso educativo — nocturno 4h', 'sku': 'teatro-edu-4h-n', 'price': 1269000},
        {'name': 'Uso cultural — nocturno 4h', 'sku': 'teatro-cult-4h-n', 'price': 1587000},
        {'name': 'Uso empresarial — nocturno 4h', 'sku': 'teatro-emp-4h-n', 'price': 1650000},
        {'name': 'Uso comercial — nocturno 4h', 'sku': 'teatro-com-4h-n', 'price': 1905000},
    ],
    requires_booking=True,
    tags=['alquiler', 'teatro', 'eventos'])

# ── RECREACIÓN DIRIGIDA ───────────────────────────────────────────────────────
print('\n— RECREACIÓN DIRIGIDA —')

svc('Personaje animado (3 horas, máx. 60 niños)',
    category='Recreacion Dirigida',
    description='Operador disfrazado de personaje de serie infantil o animada. Duración 3 horas, '
                'máx. 60 personas. Requiere fluido eléctrico 110v y confirmación 8 días antes.',
    variants=variants((63000, 72000, 115700, 135000, 144000), 'rec-personaje'),
    requires_booking=True,
    tags=['recreacion-dirigida', 'eventos-infantiles'])

svc('Inflable Parque Saltarín (3 horas, máx. 400 niños 5-12 años)',
    category='Recreacion Dirigida',
    description='Inflable parque saltarín para niños de 5 a 12 años. 3 horas. '
                'Requiere fluido 110v y área de 6x6 m con sombra.',
    variants=variants((153000, 182800, 271700, 293000, 315000), 'rec-inflable-saltarin'),
    requires_booking=True,
    tags=['recreacion-dirigida', 'eventos-infantiles', 'inflable'])

svc('Karaoke recreativo (2 horas, máx. 60 personas)',
    category='Recreacion Dirigida',
    description='Karaoke con pantalla gigante y animadores. 2 horas, máx. 60 personas. '
                'Incluye video beam, telón, parlante y micrófono.',
    variants=variants((190000, 201000, 275100, 304000, 331000), 'rec-karaoke'),
    requires_booking=True,
    tags=['recreacion-dirigida', 'karaoke'])

svc('Bingo recreativo (3 horas, 100 pax)',
    category='Recreacion Dirigida',
    description='Bingo animado para adultos y niños. Capacidad 100 personas, 3 horas. '
                'Incluye: 2 animadores, 100 tablas, balotera y sonido.',
    variants=variants((208000, 219000, 448500, 491000, 511000), 'rec-bingo'),
    requires_booking=True,
    tags=['recreacion-dirigida', 'bingo'])

# ── Summary ───────────────────────────────────────────────────────────────────
total = Product.objects.filter(organization=org).count()
variants_total = sum(p.variants.count() for p in Product.objects.filter(organization=org))
print(f'\nTotal productos: {total} | Total variantes: {variants_total}')

from collections import Counter
cats = Counter(Product.objects.filter(organization=org).values_list('category', flat=True))
print('\nPor categoría:')
for c, n in sorted(cats.items()):
    print(f'  {c}: {n}')
