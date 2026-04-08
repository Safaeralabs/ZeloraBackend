"""
Populates Comfaguajira KB with the complete 2026 Portafolio de Productos y Tarifas.
Run:  py scripts/populate_comfaguajira_tarifario_2026.py

This script REPLACES all previous KB articles for the Comfaguajira org.
"""
import django
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.knowledge_base.models import KBArticle
from apps.accounts.models import Organization

ORG_ID = 'd620ebfb-71b3-48f6-ab9e-1f187f93d9fb'
org = Organization.objects.get(id=ORG_ID)
print(f'Org: {org.name}')

# ── Wipe previous articles ────────────────────────────────────────────────────
deleted, _ = KBArticle.objects.filter(organization=org).delete()
print(f'Deleted {deleted} existing articles.')

# ── Helpers ───────────────────────────────────────────────────────────────────
def art(title, content, purpose='faq', category='tarifario-2026', tags=None):
    return dict(title=title, content=content, purpose=purpose,
                category=category, tags=tags or [])


# ── Article definitions ───────────────────────────────────────────────────────
ARTICLES = [

    # =========================================================
    # BUSINESS (quién es Comfaguajira / por qué elegirnos)
    # =========================================================
    art(
        title='Qué es Comfaguajira y cómo funciona',
        purpose='business',
        category='general',
        content="""\
Comfaguajira es la Caja de Compensación Familiar del departamento de La Guajira, Colombia.
Brinda servicios integrales de bienestar social a trabajadores afiliados y sus familias:
recreación, turismo, salud, educación, crédito social, vivienda, cultura, deportes y
programas especiales como Adulto Mayor, Discapacidad y Crecer Sano.

SISTEMA DE CATEGORÍAS (Decreto 827 de 2003)
La tarifa que paga cada afiliado depende de su salario:
  Categoría A: salario ≤ 2 SMLV → mayor subsidio (tarifas más bajas)
  Categoría B: salario entre 2 y 4 SMLV → subsidio medio
  Categoría C: salario > 4 SMLV → menor subsidio
  Empresa Afiliada: empresa inscrita que compra el servicio para sus empleados
  Particular / No Afiliado: público general, sin subsidio

Para acceder con tarifa de afiliado es indispensable presentar la cédula de ciudadanía.
Las empresas afiliadas deben estar a paz y salvo con sus aportes.

SEDES Y CENTROS
  • Sede administrativa: Calle 13 # 8-175, Riohacha
  • Centro Socio Cultural y Recreativo Anas Mai: Riohacha
  • Centro Recreacional y Vacacional Maziruma: Dibulla
  • Polideportivo Hatonuevo: Hatonuevo
  • Teatro Akuaipaa: Riohacha
  • Centro de Desarrollo Educativo Comfaguajira: Riohacha
  • Institución Educativa Comfamiliar N.º 1: Hatonuevo
  • CEFPAC (adultos por ciclos): Riohacha
  • Oficina de Crédito Social: Calle 13 # 8-175, ext. 5000/5001/5002

FORMAS DE PAGO GENERAL
Efectivo, tarjeta débito, tarjeta crédito, consignación bancaria.
Cuenta Bancolombia (Anas Mai / Maziruma): 526-00004229
Cuenta Banco Colombia (Crédito): 5267836462-2
"""),

    art(
        title='Portafolio completo de servicios 2026',
        purpose='business',
        category='general',
        content="""\
RESUMEN DE TODOS LOS SERVICIOS COMFAGUAJIRA 2026

1. CRÉDITO SOCIAL — préstamos a tasas 1.3-1.6% mensual hasta 60 cuotas
2. NUTRICIÓN CRECER SANO — consultas y fórmulas lácteas subsidiadas para niños 6 meses-14 años
3. EDUCACIÓN PARA EL TRABAJO — talleres, cursos, diplomados, formación laboral técnica
4. EDUCACIÓN FORMAL — Institución Educativa en Hatonuevo (preescolar a media)
5. EDUCACIÓN PARA ADULTOS POR CICLOS — CEFPAC (ciclos 1 a 6)
6. ALQUILER ESPACIOS EDUCATIVOS — aulas y auditorio en Centro Desarrollo Educativo
7. TEATRO AKUAIPAA — alquiler para eventos culturales, educativos y empresariales
8. ADULTO MAYOR — programa mensual "La Edad de Trigo" con actividades en Riohacha y municipios
9. DISCAPACIDAD — programa mensual de inclusión sociolaboral
10. CULTURA / ESCUELA DE ARTES — pintura, música, teatro y danza
11. VIVIENDA — subsidio de vivienda rural/urbano y certificados de elegibilidad
12. SALUD IPS — consultas generales, especializadas, laboratorio, terapias
13. RECREACIÓN ANAS MAI (Riohacha) — pasadías, alquiler de espacios, eventos
14. RECREACIÓN MAZIRUMA (Dibulla) — pasadías, alojamiento, alquiler de espacios
15. RECREACIÓN POLIDEPORTIVO HATONUEVO — pasadías con transporte
16. TURISMO SOCIAL — Cabo de la Vela, Rancherías, Santuario Flora y Fauna, Tierra Guajira, Mayapo, Palomino
17. RECREACIÓN DIRIGIDA — personajes, inflables, karaoke, recreacionistas, eventos
18. DEPORTES — torneos, escuelas deportivas, gimnasio, actividades acuáticas
19. ALIMENTOS Y BEBIDAS — Restaurante Perla Mar (Anas Mai), menús de pasadía y eventos
"""),

    # =========================================================
    # CRÉDITO SOCIAL
    # =========================================================
    art(
        title='Crédito Social — tasas, plazos y líneas 2026',
        category='credito-social',
        content="""\
SERVICIO DE CRÉDITO SOCIAL 2026
Costo del estudio de crédito: $20.000 (no reembolsable)

LÍNEAS DE CRÉDITO — TASAS EFECTIVA MENSUAL VENCIDA
(el plazo máximo puede ser por Libranza o por Pignoración)

Línea         | Plazo Libranza | Plazo Pignoración | Cat A  | Cat B  | Cat C
SALUD         |   36 meses     |   12 meses        | 1,4%   | 1,5%   | 1,6%
RECREACIÓN    |   36 meses     |   12 meses        | 1,4%   | 1,5%   | 1,6%
TURISMO       |   48 meses     |   12 meses        | 1,4%   | 1,5%   | 1,6%
EDUCACIÓN     |   36 meses     |   12 meses        | 1,4%   | 1,5%   | 1,6%
LIBRE INVERSIÓN|  60 meses     |   12 meses        | 1,4%   | 1,5%   | 1,6%
COMPRA CARTERA|   60 meses     |   N/A             | 1,3%   | 1,4%   | 1,4%

Las tasas se convierten a su equivalente según la necesidad del afiliado.

NOTAS IMPORTANTES
• El crédito se descuenta directamente por nómina (libranza) o por pignoración del subsidio.
• El monto aprobado depende de la capacidad de pago del afiliado.
• Si el trabajador se desafilia, el saldo puede hacerse exigible.
• Para el crédito de Educación para Adultos por ciclos: dirigirse a la Oficina de Crédito Social,
  Calle 13 # 8-175, ext. 5000-5001-5002.

REQUISITOS GENERALES
Cédula de ciudadanía, certificado laboral, últimas colillas de pago.
Contacto: ext. 5000/5001/5002 — Sede administrativa Calle 13 # 8-175, Riohacha.
"""),

    # =========================================================
    # NUTRICIÓN — CRECER SANO
    # =========================================================
    art(
        title='Programa Nutrición Crecer Sano — tarifas 2026',
        category='nutricion',
        content="""\
PROGRAMA CRECER SANO — Nutrición Ley 21 del 82

QUÉ ES
Programa que alivia el desequilibrio económico familiar causado por el embarazo, el nacimiento
y la desnutrición. Opera a través de un subsidio en especie (consulta nutricional + fórmulas lácteas).
Dirigido a afiliados Categoría A y B, para niños de 6 meses a 14 años.

CONSULTA DE NUTRICIÓN
  Tarifa plena: $35.324
  Afiliados Cat A y B: $13.000 (subsidio del 63% sobre el costo total)

FÓRMULAS LÁCTEAS — PAQUETES DE 5 UNIDADES (tarifa para Cat A y B)
Los afiliados Cat A y B reciben un subsidio del 75% sobre la tarifa total de cada fórmula.

Fórmula                               | Tarifa Cat A/B (paquete x5)
BABY KLIM 400 g                       | $76.200
BABY KLIM 800 g                       | $95.100
NUTRI ADVANCE                         | $91.300
KLIM 1+                               | $47.400
KLIM 1+ DESLACTOSADA x800             | $102.600
KLIM 3+                               | $41.200
NAN AE                                | $123.100
NAN AR                                | $147.600
NAN CONFORT                           | $159.400
NAN OPTIPRO 2 pote x 400 g            | $121.100
NAN SIN LACTOSA                       | $136.900
NESTOGENO 2 x400                      | $63.000
NESTOGENO COMFORT                     | $94.900
EL RODEO                              | $32.900
KLIM DESLACTOSADA                     | $63.100
KLIM FORTIFICADA                      | $42.300
EL RODEO ESENCIAL x600 g              | $80.100
NAN OPTIPRO 2 pote x 900 g            | $241.900
NESTOGENO 3 x800 g                    | $149.900
SIMILAC 2 x350 g                      | $153.400
SIMILAC 3 x350 g                      | $149.400
BABY ALPINA 2 x400 g                  | $93.400
LECHE ENTERA INDULECHES x360 g        | $44.600
ASCENDA x900 g                        | $302.400
ENFAMIL PREMIUM 2 x375 g              | $246.400
ENFAGROW PREMIUM 3 x375 g             | $213.900
ALULA GOLD PREMIUM 2 x400 g           | $233.400
ALULA GOLD PREMIUM 3 x400 g           | $208.100
NUTRIBEN AE2                          | $130.900
NUTRIBEN AR                           | $140.100
NUTRIBEN BAJO PESO                    | $136.600
NUTRIBEN CONFORT                      | $140.100
NUTRIBEN CONTINUACION 2 lata x400 g   | $122.600
NUTRIBEN CRECIMIENTO 3 lata x400 g    | $108.100
NUTRIBEN HIDROLIZADA 2                | $279.400
NUTRIBEN SIN LACTOSA                  | $140.100

MODALIDADES DEL BONO
• Paquete de 5 potes/bolsas (presentaciones 380, 400, 500, 800 y 900 g) — subsidio 75%
• Paquete de 3 potes/bolsas — subsidio 75%
• Paquete de 2 potes/bolsas — subsidio 75%
Las tarifas para 2 o 3 unidades se establecen proporcionalmente.
"""),

    # =========================================================
    # EDUCACIÓN INFORMAL
    # =========================================================
    art(
        title='Educación Informal — talleres, cursos y diplomados 2026',
        category='educacion',
        content="""\
PROGRAMA EDUCACIÓN INFORMAL 2026
Incluye: Honorarios docente, salón (talleres/seminarios hasta 10 h).
Cursos 20-40 h también incluyen refrigerio.
Capacidad máxima: 25 personas por grupo.

TALLERES Y SEMINARIOS (hasta 10 horas)
Temáticas: responsabilidad laboral, comunicación asertiva y efectiva, liderazgo, inteligencia
emocional, manejo del cambio organizacional, trabajo en equipo, manejo del tiempo, empatía,
resolución de conflictos, manejo del estrés, toma de decisiones, entre otras.

Servicio                 | Cat A  | Cat B  | Cat C   | Emp.Afil.| Particular
TALLER 1 HORA            |  $0    |  $0    | $10.300 | $11.300  | $12.300
TALLER 2 HORAS           |  $0    |  $0    | $20.100 | $22.100  | $24.100
TALLER 4 HORAS           | $25.200| $30.500| $39.800 | $45.200  | $51.600
SEMINARIO 8 HORAS        | $41.300| $46.700| $64.100 | $73.800  | $78.200
SEMINARIO 10 HORAS       | $50.700| $57.400| $79.300 | $91.200  | $97.400

CURSOS DE 20 Y 40 HORAS
Incluye: honorarios docente, refrigerio, salón.
Temáticas 20-40 h: Wayuunaiki básico, emprendimiento, creatividad e innovación, marketing digital,
servicio al cliente, servicios generales, técnicas de ventas, contabilidad y finanzas,
redacción de informes ejecutivos, gestión documental, elaboración de presupuesto empresarial,
informática básica y avanzada, Excel básico y avanzado, entre otras.

Servicio                       | Cat A  | Cat B   | Cat C    | Emp.Afil. | Particular
CURSO 20 HORAS                 | $98.800|$113.400 | $154.400 | $176.400  | $193.700
CURSO 40 HORAS                 |$180.600|$207.900 | $285.300 | $326.500  | $355.800
CURSOS PRODUCTIVOS 40 HORAS    |$161.200|$183.900 | $252.000 | $288.700  | $317.900

CURSOS PRODUCTIVOS 40, 60 Y 80 HORAS
Incluye: honorarios docente, material educativo, salón.
Temáticas 40 h: Depilación facial y corporal, diseño y perfilación de cejas semipermanentes,
extensión de pestañas punto a punto, corte de cabello, manicure y pedicure, patronaje industrial I-IV
(faldas, blusas, vestidos, pantalones), costura básica, transformación y arreglos de ropa en casa.
Temáticas 60 h: Masaje relajante y terapias.
Temáticas 80 h: Wayuunaiki avanzado.

Servicio                         | Cat A   | Cat B   | Cat C    | Emp.Afil. | Particular
CURSOS PRODUCTIVOS 60 HORAS      |$226.800 |$260.300 | $356.400 | $408.200  | $444.600
CURSOS PRODUCTIVOS 80 HORAS      |$283.400 |$323.600 | $444.900 | $512.300  | $558.200

DIPLOMADOS ESPECIALIZADOS (hasta 230 horas)
Incluye: honorarios docentes especializados, material educativo digital. Capacidad máx. 30 personas.
Temáticas: Docencia universitaria, gestión de formación con TIC, pedagogías inclusivas, educación
primera infancia, habilidades comerciales, gestión financiera, negocios digitales y e-commerce.

Servicio                           | Cat A     | Cat B     | Cat C       | Emp.Afil.  | Particular
DIPLOMADO 80 HORAS                 | $586.500  | $671.800  | $920.200    | $1.059.200 | $1.154.000
DIPLOMADO 120 HORAS                | $862.000  | $987.000  | $1.357.500  | $1.561.200 | $1.702.000
DIPLOMADO 230 HORAS                |$1.425.400 |$1.629.500 | $2.036.600  | $2.749.800 | $3.054.800

CONGRESOS
Servicio                        | Cat A   | Cat B   | Cat C   | Emp.Afil.| Particular
CONGRESO NACIONAL 20 HORAS      | $432.500| $540.700| $702.900| $735.300 | $756.900
"""),

    # =========================================================
    # FORMACIÓN LABORAL
    # =========================================================
    art(
        title='Formación Laboral — técnicos laborales, seminarios y derechos académicos 2026',
        category='educacion',
        content="""\
PROGRAMA FORMACIÓN LABORAL 2026

PROGRAMAS TÉCNICO LABORAL (600 a 1.200 horas — hasta 4 semestres)
Formación para el trabajo y el desarrollo humano.

TARIFA SEMESTRE
Cat A: $182.400 | Cat B: $369.100 | Cat C: $675.200 | Emp. Afil.: $706.000 | Particular: $759.900

TARIFA TRIMESTRE (pago trimestral)
Cat A: $91.200 | Cat B: $184.550 | Cat C: $337.600 | Emp. Afil.: $353.000 | Particular y No Afil.: $379.950

DIPLOMADO DE GRADO PARA TÉCNICOS LABORALES
Servicio                                     | Cat A   | Cat B   | Cat C   | Emp.Afil.| Particular
Diplomado técnicos laborales 80 h (presencial)|$129.500 |$227.600 |$347.900 | $375.000 | $422.100
Diplomado técnicos laborales 120 h (presencial)|$183.100|$320.600 |$484.800 | $542.000 | $634.400

SEMINARIOS DE PROFUNDIZACIÓN
Servicio                                    | Cat A  | Cat B  | Cat C  | Emp.Afil.| Particular
Seminario profundización 12 h (presencial)  | $26.400| $45.500| $73.500| $75.000  | $96.800
Seminario profundización 20 h (presencial)  | $33.200| $54.500| $86.900| $103.000 | $119.000
Seminario profundización 40 h (presencial)  | $66.400|$109.000|$173.900| $183.000 | $238.000

SEMINARIOS EN EMPRENDIMIENTO
Servicio                           | Cat A  | Cat B  | Cat C  | Emp.Afil.| Particular
Seminario técnico emprende 8 h     | $25.600| $37.200| $54.200| $58.000  | $62.000
Seminario técnico emprende 10 h    | $36.500| $66.800| $99.500| $102.000 | $107.500

SEMINARIO DE ACTUALIZACIÓN
Servicio                           | Cat A  | Cat B  | Cat C  | Emp.Afil.| Particular
Seminario de actualización 6 h     | $10.200| $17.500| $27.100| $32.000  | $37.900

TARIFAS COMPLEMENTARIAS Y DERECHOS ACADÉMICOS
Concepto                                  | Cat A   | Cat B   | Cat C    | Emp.Afil. | D/Particular
Validación Cursos Técnicos Laborales      | $36.600 | $72.900 | $140.500 | $151.400  | $164.700
Homologación Cursos Técnicos Laborales    | $23.600 | $60.000 | $115.600 | $119.000  | $124.700
Derecho a Grado Programas Técnicos Labor. | $355.400| $355.400| $410.400 | $421.200  | $453.600
Reintegro Cursos Técnicos Laborales       | $24.900 | $24.900 | $54.000  | $54.000   | $59.400
Inscripción Técnicos Laborales            | $24.900 | $24.900 | $37.800  | $37.800   | $48.600

TARIFAS DERECHOS ACADÉMICOS
Concepto                                  | Cat A   | Cat B   | Cat C    | Emp.Afil. | D/Particular
Duplicado Carnet Estudiantil              | $16.500 | $16.500 | $27.000  | $27.000   | $28.100
Asignatura vista por segunda vez          | $57.800 | $57.800 | $81.000  | $81.500   | $82.000
Certificados de Notas Técnico Laborales   | $15.400 | $15.400 | $21.600  | $21.600   | $23.700
Duplicados de Diplomado y acta de grado   | $88.600 | $88.600 | $108.000 | $118.800  | $129.600
Habilitación/Supletorio Técnicos Labor.   | $32.500 | $32.500 | $48.600  | $48.600   | $49.600
"""),

    # =========================================================
    # EDUCACIÓN FORMAL
    # =========================================================
    art(
        title='Educación Formal — Institución Hatonuevo y matrícula 2026',
        category='educacion',
        content="""\
INSTITUCIÓN EDUCATIVA COMFAMILIAR DE LA GUAJIRA N.º 1 — HATONUEVO
Tarifas de matrícula y pensión mensual por categoría

PREESCOLAR — Párvulo, Prejardín y Jardín
Concepto     | Cat A   | Cat B   | Cat C    | Empresas  | Particular
MATRÍCULA    | $393.400| $425.900| $652.000 | $691.000  | $698.500
PENSIÓN MES  | $112.000| $128.000| $241.600 | $260.000  | $265.000

PREESCOLAR — Transición
Concepto     | Cat A   | Cat B   | Cat C    | Empresas  | Particular
MATRÍCULA    | $398.800| $430.300| $652.000 | $691.000  | $698.500
PENSIÓN MES  | $114.800| $130.500| $241.600 | $260.000  | $265.000

BÁSICA PRIMARIA
Concepto     | Cat A   | Cat B   | Cat C    | Empresas  | Particular
MATRÍCULA    | $430.400| $469.600| $832.000 | $891.000  | $897.000
PENSIÓN MES  | $130.000| $150.000| $331.900 | $358.000  | $364.000

BÁSICA SECUNDARIA
Concepto     | Cat A   | Cat B   | Cat C    | Empresas  | Particular
MATRÍCULA    | $508.700| $560.900| $893.000 | $955.000  | $963.200
PENSIÓN MES  | $169.900| $195.900| $361.600 | $390.000  | $397.100

MEDIA ACADÉMICA
Concepto     | Cat A   | Cat B   | Cat C    | Empresas  | Particular
MATRÍCULA    | $517.400| $569.600| $893.000 | $963.200  | $955.000
PENSIÓN MES  | $174.000| $200.000| $361.600 | $397.100  | $390.000

OTROS COSTOS ACADÉMICOS (Institución Hatonuevo)
Concepto                         | Tarifa
Inscripción                      | $21.600
Derecho a grado Transición       | $441.100
Derecho a grado Quinto           | $478.500
Derecho a grado Once             | $702.900
Certificado de Estudio           | $17.600
Otros costos académicos          | $169.000
"""),

    art(
        title='Educación para Adultos por Ciclos — CEFPAC 2026',
        category='educacion',
        content="""\
EDUCACIÓN FORMAL PARA ADULTOS POR CICLOS — CEFPAC
Centro CEFPAC — Riohacha, La Guajira

QUÉ ES
Centro privado con sentido social para formación de adultos, estructurado por ciclos académicos
de acuerdo con la normativa vigente.

JORNADAS
  Sábados: 7:00 a.m. a 3:00 p.m.
  Nocturno: 6:00 p.m. a 8:15 p.m.

TARIFAS ANUALES Y SEMESTRALES POR CATEGORÍA

Ciclo                              | Duración     | Cat A   | Cat B   | Cat C      | Emp.Afil.  | Cat D
CICLO 1 (Grados 1-3 primaria)     | 1 año escolar| $322.000| $578.000| $1.519.000 | $1.681.000 | $1.822.000
CICLO 2 (Grados 4-5 primaria)     | 1 año escolar| $322.000| $578.000| $1.519.000 | $1.681.000 | $1.822.000
CICLO 3 (Grados 6-7 secundaria)   | 1 año escolar| $322.000| $578.000| $1.519.000 | $1.681.000 | $1.822.000
CICLO 4 (Grados 8-9 secundaria)   | 1 año escolar| $322.000| $578.000| $1.519.000 | $1.681.000 | $1.822.000
CICLO 5 (Grado 10)                | Semestre     | $161.000| $289.000| $759.400   | $841.000   | $911.000
CICLO 6 (Grado 11)                | Semestre     | $161.000| $289.000| $759.400   | $841.000   | $911.000

TARIFA APOYO PSICOSOCIAL
  Ciclo anual:     $1.044.500 por persona
  Ciclo semestral: $522.300 por persona
Incluye: material educativo, transporte, uniforme, alimentación y fortalecimiento académico.

REQUISITOS PARA MATRÍCULA
  • Formulario de inscripción y matrícula
  • Fotocopia del documento de identidad
  • Dos (2) fotografías tamaño carnet fondo azul
  • Certificado de estudio con notas (en original) del último grado aprobado
  • Certificado de seguro médico EPS, régimen subsidiado o ADRES
  • Documento de retiro del SIMAT de la institución anterior
  • Documento que evidencie pertenencia a: víctimas, negritudes o indígenas (si aplica)
  • En caso de discapacidad: soportes de la condición (si aplica)
  • Observatorio o certificado de conducta (aplica para menores de 19 años)
  • Carpeta colgante

MODALIDADES DE PAGO
  1. Crédito de Educación por libranza para afiliados — tramitar en Oficina de Crédito Social
     (Calle 13 # 8-175, ext. 5000-5001-5002)
  2. En efectivo — cajas de la sede o consignación Bancolombia cuenta ahorros 5267836462-2
"""),

    # =========================================================
    # ALQUILER ESPACIOS EDUCATIVOS
    # =========================================================
    art(
        title='Alquiler de espacios Centro Desarrollo Educativo 2026',
        category='alquiler-espacios',
        content="""\
ALQUILER DE ESPACIOS — CENTRO DE DESARROLLO EDUCATIVO COMFAGUAJIRA
Tarifas incluyen IVA 19%

INCLUYE: Sillas universitarias acolchadas con brazo, aire acondicionado, tablero acrílico,
2 marcadores, vigilancia e IVA.
Ayudas audiovisuales y computador portátil: sujetos a disponibilidad y solicitud del cliente.

PARA ACCEDER A TARIFA DE AFILIADO es indispensable presentar la cédula de ciudadanía.
Empresas afiliadas deben estar a paz y salvo con sus aportes.

1 JORNADA — 4 HORAS (Tarifas año 2026 por categoría)
Espacio        | Cat A   | Cat B   | Cat C   | Emp.Afil.| Particular
Aula S-01      | $136.000| $146.000| $180.000| $212.000 | $223.000
Aula S-02      | $87.000 | $94.000 | $116.000| $136.000 | $144.000
Aula S-03      | $129.000| $138.000| $168.000| $197.000 | $209.000
Aula S-04      | $118.000| $127.000| $155.000| $181.000 | $192.000
Aula S-05      | $118.000| $127.000| $155.000| $181.000 | $192.000
Aula S-06      | $111.000| $119.000| $145.000| $171.000 | $180.000
Aula 1-01      | $138.000| $149.000| $182.000| $215.000 | $227.000
Aula 1-02      | $148.000| $159.000| $195.000| $230.000 | $243.000
Auditorio      | $274.000| $294.000| $355.000| $416.000 | $441.000
Aula 2-01      | $146.000| $157.000| $192.000| $227.000 | $239.000
Aula 2-02      | $146.000| $156.000| $192.000| $227.000 | $239.000
Aula 2-03      | $163.000| $176.000| $216.000| $255.000 | $269.000
Aula 2-04      | $154.000| $166.000| $203.000| $239.000 | $253.000
Aula 2-05      | $146.000| $156.000| $192.000| $227.000 | $239.000
Aula 2-06      | $146.000| $157.000| $192.000| $227.000 | $239.000
Aula 2-07      | $142.000| $154.000| $188.000| $221.000 | $234.000
Patio Tertulias|  $62.000|  $69.000|  $91.000|  $99.000 | $114.000

2 JORNADAS — 8 HORAS (Tarifas año 2026 por categoría — las 8h refieren al año 2024 en el tarifario original)
Espacio        | Cat A   | Cat B   | Cat C   | Emp.Afil.| Particular
Aula S-01      | $272.000| $293.000| $359.000| $385.000 | $446.000
Aula S-02      | $175.000| $189.000| $232.000| $247.000 | $287.000
Aula S-03      | $257.000| $277.000| $337.000| $359.000 | $419.000
Aula S-04      | $236.000| $253.000| $309.000| $330.000 | $383.000
Aula S-05      | $236.000| $253.000| $309.000| $330.000 | $383.000
Aula S-06      | $222.000| $238.000| $290.000| $310.000 | $360.000
Aula 1-01      | $276.000| $297.000| $365.000| $390.000 | $454.000
Aula 1-02      | $296.000| $319.000| $391.000| $418.000 | $485.000
Auditorio      | $549.000| $587.000| $710.000| $757.000 | $883.000
Aula 2-01      | $291.000| $314.000| $385.000| $412.000 | $479.000
Aula 2-02      | $291.000| $312.000| $385.000| $412.000 | $479.000
Aula 2-03      | $326.000| $352.000| $432.000| $463.000 | $537.000
Aula 2-04      | $308.000| $331.000| $407.000| $435.000 | $506.000
Aula 2-05      | $291.000| $312.000| $385.000| $412.000 | $479.000
Aula 2-06      | $291.000| $314.000| $385.000| $412.000 | $479.000
Aula 2-07      | $285.000| $307.000| $377.000| $403.000 | $469.000
Patio Tertulias| $124.000| $138.000| $182.000| $197.000 | $229.000
"""),

    art(
        title='Teatro Akuaipaa — tarifas de alquiler 2026',
        category='alquiler-espacios',
        content="""\
TEATRO AKUAIPAA — ALQUILER DE ESPACIO
Clasificaciones: Educativo | Cultural | Empresarial | Comercial

OBSERVACIONES IMPORTANTES
• Se debe diligenciar el formato de solicitud del servicio describiendo el tipo de evento.
  La clasificación determina la tarifa aplicable.
• El valor incluye el tiempo de adecuaciones, decoración y organización del evento.
  El montaje debe realizarse dentro del tiempo establecido.
• NO se presta el espacio para decoración anticipada antes del tiempo alquilado.
• TODO tiempo adicional de uso debe ser pagado según tarifas vigentes.
• Tarifas nocturnas y fines de semana tienen recargos adicionales.
• NO se permite consumir alimentos ni bebidas al interior del teatro.
• Para reservar el teatro es obligatorio pagar el 50% del valor al momento de la reserva.

2 JORNADAS — 8 HORAS
Horario      | Educativo   | Cultural    | Empresarial | Comercial
DIURNO       | $2.114.800  | $2.644.000  | $2.750.000  | $3.173.000
NOCTURNO     | $2.538.000  | $3.173.000  | $3.300.000  | $3.808.000

1 JORNADA — 6 HORAS
Horario      | Educativo   | Cultural    | Empresarial | Comercial
DIURNO       | $1.744.800  | $2.181.000  | $2.269.000  | $2.618.000
NOCTURNO     | $2.094.000  | $2.618.000  | $2.723.000  | $3.142.000

1 JORNADA — 4 HORAS
Horario      | Educativo   | Cultural    | Empresarial | Comercial
DIURNO       | $1.057.400  | $1.322.000  | $1.375.000  | $1.587.000
NOCTURNO     | $1.269.000  | $1.587.000  | $1.650.000  | $1.905.000

Inicio horario nocturno: 7:00 p.m.
Fin horario nocturno: 6:00 a.m.
"""),

    # =========================================================
    # ADULTO MAYOR Y DISCAPACIDAD
    # =========================================================
    art(
        title='Programa Adulto Mayor — tarifas y actividades 2026',
        category='adulto-mayor',
        content="""\
PROGRAMA ADULTO MAYOR 2026

TARIFAS MENSUALES
Servicio                                   | Cat A  | Cat B  | Cat C   | Cat D
Mensualidad Programa Adulto Mayor permanente| $5.900 | $11.800| $60.700 | $65.400
Mensualidad Programa Adulto Mayor itinerante| $0     | $0     | $45.300 | $67.900

NOTA: Las actividades itinerantes son 100% subsidiadas para las categorías A y B activas.

PROGRAMA "LA EDAD DE TRIGO" — RIOHACHA
Tarifa mensual. Incluye tres componentes:

1. ACTIVIDADES DE PROMOCIÓN Y PREVENCIÓN EN SALUD FÍSICA
   • Valoración médica de ingreso (presencial)
   • Actividad física
   • Sopa de letras
   • Apoyo psicosocial

2. ACTIVIDADES DE EDUCACIÓN
   • Taller de manualidades
   • Taller de dibujo y pintura
   • Taller de danza
   • Cuentos y anécdotas
   • Encuentro espiritual
   • Taller de lectura
   • Taller de crecimiento personal

3. ACTIVIDADES DE RECREACIÓN
   • Tarde de cine
   • Caminatas ecológicas
   • Celebración de cumpleaños
   • Pasadías Anas Mai
   • Pasadías a otros municipios
   • Celebración Día de las Madres
   • Tarde de playa
   • Rumba terapia
   • Recreación dirigida
   • Juegos de mesa
   • Bingo

ACTIVIDADES ITINERANTES — ADULTO MAYOR EN MUNICIPIOS
Estrategia para ampliar cobertura en todos los municipios del departamento.
Programadas y ejecutadas en sitios de fácil acceso, con publicidad y convocatoria pública.
Zonas: Norte (Maicao, Manaure, Uribia), Sur (Villanueva, El Molino, San Juan, Fonseca, Barrancas, Hatonuevo)
       y Troncal del Caribe (Dibulla, Palomino).
"""),

    art(
        title='Programa Discapacidad — tarifas y componentes 2026',
        category='discapacidad',
        content="""\
PROGRAMA DISCAPACIDAD 2026

TARIFAS MENSUALES
Servicio                              | Cat A | Cat B | Cat C    | Cat D
Programa Discapacidad permanentes     | $0    | $0    | $229.200 | $243.200
Actividades Itinerantes Discapacidad  | $0    | $0    | $144.600 | $188.000

DESCRIPCIÓN DEL PROGRAMA
Tarifa mensual que incluye dos componentes:

1. INCLUSIÓN SOCIOLABORAL
   Promueve el cumplimiento de los derechos de la población en condición de discapacidad
   afiliada a Comfaguajira, para que lleven una vida independiente y activa en la comunidad.

2. DESARROLLO DE CAPACIDADES Y GENERACIÓN DE OPORTUNIDADES
   Apoya el desarrollo de potencialidades de la población en condición de discapacidad,
   mediante acciones de educación, formación, bienestar, salud, desarrollo vocacional,
   ocupacional y laboral, junto con sus familias.
"""),

    # =========================================================
    # CULTURA — ESCUELA DE ARTES
    # =========================================================
    art(
        title='Escuela de Artes Comfaguajira — tarifas 2026',
        category='cultura',
        content="""\
ESCUELA DE ARTES COMFAGUAJIRA 2026
Dirigida a afiliados y comunidad en general. Dirigida a personas a partir de 7 años.
Modalidad: presencial. Certificación: de participación y/o cursó la modalidad y el nivel.

DURACIÓN: 1 nivel = 32 horas académicas (hasta 6 horas semanales)
JORNADAS: Diurna, nocturna y sabatina (aplican condiciones)

REQUISITOS DE ADMISIÓN
  • Proceso de inscripción y/o matrícula
  • Fotocopia del documento de identidad
  • Certificación de afiliación a EPS, ARS o SISBEN (no mayor a 30 días)
  • Dos (2) fotografías 3x4 a color
  • Entrevista personal

CURSOS ESCUELA DE PINTURA
Nivel | Descripción           | Cat A  | Cat B  | Cat C    | Emp.Afil.| Particular
1     | Lápiz                 | $48.600| $55.000| $207.400 | $307.000 | $337.000
2     | Tempera y/o acuarela  | $60.500| $68.000| $256.000 | $371.600 | $410.400
3     | Óleo                  | $67.000| $77.000| $288.400 | $419.000 | $458.000

CURSOS ESCUELA DE MÚSICA (32 h por nivel)
Nivel | Descripción                | Cat A  | Cat B  | Cat C    | Emp.Afil.| Particular
1     | Flauta y/o Guitarra        | $61.000| $69.000| $110.200 | $149.000 | $259.200
2     | Piano                      | $67.000| $77.000| $144.200 | $168.000 | $313.200
3     | Acordeón                   | $90.000|$103.000| $191.500 | $225.000 | $399.600

CURSO ESCUELA DE TEATRO (32 h)
Modalidad | Cat A  | Cat B  | Cat C    | Emp.Afil.| Particular
Teatro    | $58.400| $66.000| $246.300 | $363.000 | $397.500

CURSO ESCUELA DE DANZA (32 h)
Modalidad | Cat A  | Cat B  | Cat C    | Emp.Afil.| Particular
Danza     | $63.000| $71.300| $266.000 | $393.200 | $423.400

ANOTACIONES GENERALES
  • El usuario debe cancelar inscripción o matrícula para acceder al pago del curso.
  • Pagos por curso y nivel según tarifa por categoría.
  • Con el pago de la tarifa el usuario tiene derecho a los materiales (cuando aplique).
  • Los pagos son por curso y nivel, según categoría.
"""),

    # =========================================================
    # VIVIENDA
    # =========================================================
    art(
        title='Servicio de Vivienda — subsidios y certificados 2026',
        category='vivienda',
        content="""\
SERVICIO DE VIVIENDA COMFAGUAJIRA 2026

SUBSIDIO DE VIVIENDA URBANO — MEJORAS LOCATIVAS
Marco legal: Decreto Único Reglamentario 1077 del 2015.
La elegibilidad es la manifestación formal del concepto favorable de viabilidad para
modalidades de aplicación del subsidio que no requieren licencias de construcción.

SUBSIDIO DE VIVIENDA RURAL
Marco legal: Decreto 1071 del 2015, modificado por Decreto 1934 del 2015.
Comfaguajira cuenta con un Reglamento Operativo para postulación, asignación y legalización
del subsidio de vivienda rural.

CERTIFICADO DE ELEGIBILIDAD DE PROYECTOS DE VIVIENDA
La División del Subsidio Familiar — Coordinación de Vivienda revisa el proyecto (técnica,
financiera y legalmente) y expide el certificado de viabilidad requerido para la postulación.

TARIFAS — CERTIFICADO DE VIABILIDAD
Modalidad                          | % sobre presupuesto de obras
Construcción en lote propio rural  | 0,91%
Mejoramiento rural                 | 1,25%
Mejoramiento urbano                | 1,25%

CERTIFICADO DE EXISTENCIA Y HABITABILIDAD
(Resolución 1262 de 2004)
Permite verificar que la vivienda esté terminada con servicios instalados y funcionales.

Modalidad                        | Dentro del Municipio | Fuera del Municipio | Fuera del Dpto.
Construcción en sitio propio     | $59.400              | $95.000             | $190.000
Mejoramiento de vivienda estruct.| $59.400              | $95.000             | $190.000
Adquisición de vivienda nueva    | $59.400              | $95.000             | $190.000
"""),

    # =========================================================
    # SALUD IPS — CONSULTAS
    # =========================================================
    art(
        title='Salud IPS — consultas médicas y especializadas (tarifas particulares 2026)',
        category='salud',
        content="""\
TARIFAS PARTICULARES SALUD IPS 2026

CONSULTAS GENERALES Y ODONTOLÓGICAS
Código  | Servicio                                               | Tarifa
CME001  | Certificado médico                                     | $11.000
CM002   | Certificado de salud oral                              | $7.800
890201  | Consulta primera vez — Medicina General                | $29.800
890301  | Consulta control/seguimiento — Medicina General        | $29.800
890203  | Consulta primera vez — Odontología General             | $29.800
890303  | Consulta control/seguimiento — Odontología General     | $29.800
890206  | Consulta primera vez — Nutrición y Dietética           | $27.600
890306  | Consulta control/seguimiento — Nutrición y Dietética   | $27.600
890208  | Consulta primera vez — Psicología                      | $57.500
890308  | Consulta control/seguimiento — Psicología              | $27.600
890210  | Consulta primera vez — Fonoaudiología                  | $57.500
890310  | Consulta control/seguimiento — Fonoaudiología          | $27.600
890213  | Consulta primera vez — Terapia Ocupacional             | $57.500
890313  | Consulta control/seguimiento — Terapia Ocupacional     | $27.600
890209  | Consulta primera vez — Trabajo Social                  | $25.400
890309  | Consulta control/seguimiento — Trabajo Social          | $25.400

CONSULTAS ESPECIALIZADAS (primera vez / control)
Especialidad                           | Código 1ª vez | 1ª vez  | Código ctrl | Control
Cardiología                            | 890228        | $96.200 | 890328      | $96.200
Cirugía Oral                           | 890217        | $56.400 | 890317      | $96.200
Dermatología                           | 890242        | $96.200 | 890342      | $96.200
Endodoncia                             | 890218        | $56.400 | 890318      | $56.400
Estomatología y Cirugía Oral           | 890219        | $56.400 | 890319      | $56.400
Ginecología y Obstetricia              | 890250        | $96.200 | 890350      | $96.200
Medicina del Trabajo / SST             | 890262        | $96.200 | —           | —
Medicina Interna                       | 890266        | $96.200 | 890366      | $96.200
Ortopedia y Traumatología              | 890280        | $96.200 | 890380      | $96.200
Otorrinolaringología                   | 890282        | $96.200 | 890382      | $96.200
Pediatría                              | 890283        | $96.200 | 890383      | $96.200
Periodoncia                            | 890221        | $56.400 | 890321      | $56.400
Psiquiatría                            | —             | —       | 890384      | $144.800
Urología                               | 890294        | $96.200 | 890394      | $96.200
Otras especialidades médicas           | 890202        | $96.200 | 890302      | $96.200
Otras especialidades odontológicas     | 890204        | $56.400 | 890304      | $56.400
Otras especialidades de Psicología     | 890297        | $72.900 | 890397      | $72.900

TERAPIAS
Código  | Servicio                                                    | Tarifa
937001  | Terapia fonoaudiológica integral                            | $27.600
937101  | Terapia fonoaudiológica — problemas de lenguaje oral/escrito | $27.600
937201  | Terapia fonoaudiológica del habla                           | $27.600
937202  | Terapia fonoaudiológica de la voz                           | $27.600
937203  | Terapia fonoaudiológica de la deglución                     | $27.600
937301  | Terapia fonoaudiológica — desórdenes auditivo-comunicativos  | $27.600
937401  | Terapia fonoaudiológica — desórdenes cognitivo-comunicativos | $27.600

MONITOREO Y PRUEBAS
Código  | Servicio                                                    | Tarifa
895001  | Monitoreo electrocardiográfico continuo (Holter)            | $169.200
895004  | Monitoreo ambulatorio de presión arterial sistémica         | $169.200
940701  | Administración de prueba neuropsicológica (cada una)        | $107.200

PAQUETES DE REHABILITACIÓN
Código  | Descripción                                                 | Tarifa
PAQREH1 | 2 veces/semana, 3 áreas                                    | $137.800
PQAREH2 | 3 veces/semana, 3 áreas                                    | $207.200
PAQREH3 | 2 veces/semana, 2 áreas                                    | $92.000
PAQREH4 | 8 veces/mes, 3 áreas (2 veces/semana)                      | $552.300
PAQREH5 | 16 veces/mes, 2 áreas (2 veces/semana)                     | $368.000
PAQREH6 | 12 veces/mes, 3 áreas (3 veces/semana)                     | $828.800
"""),

    art(
        title='Salud IPS — tarifas de laboratorio clínico 2026 (selección)',
        category='salud',
        content="""\
TARIFAS LABORATORIO CLÍNICO — SALUD IPS 2026 (selección representativa)
Todas las tarifas son particulares. Preguntar por examen específico si no aparece aquí.

Código  | Examen                                                    | Tarifa
905701  | Acetaminofén automatizado                                 | $55.280
903805  | Amilasa en suero u otros fluidos                          | $30.270
903801  | Ácido úrico en suero                                      | $17.130
903818  | Colesterol total                                          | $18.500
903815  | Colesterol HDL (alta densidad)                            | $19.760
903817  | Colesterol LDL (baja densidad) automatizado               | $19.760
903895  | Creatinina en suero u otros fluidos                       | $17.130
903824  | Creatinina en orina de 24 horas                           | $18.500
902007  | Antitrombina III funcional automatizada                   | $86.920
906002  | Antiestreptolisina O cualitativa                          | $19.760
906001  | Antiestreptolisina O cuantitativa                         | $33.210
906440  | Anticuerpos antinucleares automatizado                    | $77.350
906466  | Anticuerpos anti-citrulina IgG                            | $148.610
906610  | Antígeno específico de próstata (PSA) semiautomatizado    | $77.350
906611  | PSA fracción libre semiautomatizado                       | $77.350
906603  | Antígeno carcinoembrionario (CEA)                         | $110.570
906604  | CA 15-3 (cáncer de mama)                                  | $113.930
906605  | CA 125 (cáncer de ovario)                                 | $113.930
906606  | CA 19-9 (tubo digestivo)                                  | $181.190
901101  | Baciloscopia Ziehl-Neelsen                                | $21.230
907002  | Coprológico                                               | $15.130
907003  | Coprológico por concentración                             | $16.290
907013  | Coprológico seriado 3 muestras                            | $45.610
901206  | Coprocultivo                                              | $60.540
906207  | Dengue anticuerpos IgG                                    | $90.600
906208  | Dengue anticuerpos IgM                                    | $96.590
904503  | Estradiol                                                 | $60.540
902205  | Eritrosedimentación (VSG) automatizada                    | $6.310
907201  | Espermograma básico                                       | $60.540
903013  | Espermograma completo                                     | $93.960
904812  | Cortisol AM                                               | $90.600
904807  | Cortisol libre en orina de 24 horas                       | $90.600
908890  | Detección VPH (virus papiloma humano) molecular específico| $354.710
903820  | Creatín quinasa MB automatizada                           | $36.890
903809  | Bilirrubinas total y directa                              | $15.450
903603  | Calcio automatizado                                       | $24.070
903813  | Cloro                                                     | $15.770

Para exámenes especializados de metabolismo, genética, enzimas o inmunohistoquímica
que no aparecen en esta lista, consultar directamente en la IPS.
"""),

    # =========================================================
    # RECREACIÓN — ANAS MAI
    # =========================================================
    art(
        title='Anas Mai — entrada, pasadía y tarifas recreativas 2026',
        category='recreacion-anas-mai',
        content="""\
CENTRO SOCIO CULTURAL Y RECREATIVO ANAS MAI — RIOHACHA
Tarifas incluyen IVA 19%

ENTRADA Y USO DE PISCINA (por persona)
Tipo          | Cat A  | Cat B  | Cat C   | Emp.Afil.| Particular
Adulto        | $3.800 | $6.500 | $13.000 | $14.100  | $19.500
Menú ejecutivo pasadía recreativo (adicional): $34.560 (todas las categorías)

HORARIOS PISCINA
  Martes a viernes:           9:00 a.m. – 3:00 p.m.
  Sábado, domingo y festivos: 9:00 a.m. – 5:00 p.m.
  A partir de 5 años todo niño cancela el plan.
  Vestido de baño reglamentario (licra de algodón o similar) obligatorio.

PASADÍA ANAS MAI SIN TRANSPORTE (comida + entrada al centro)
Categoría A: $38.400 | Cat B: $41.000 | Cat C: $48.000 | Emp. Afil.: $49.000 | Particular: $54.000
Incluye: almuerzo tipo asado, entrada al centro con derecho a piscinas (no incluye canchas deportivas).

PASADÍA ANAS MAI CON TRANSPORTE DESDE MUNICIPIOS
Ruta                        | Cat A  | Cat B  | Cat C   | Emp.Afil.| Particular
Maicao → Anas Mai           | $56.000| $62.000| $97.000 | $102.000 | $111.000
Manaure, Uribia → Anas Mai  | $60.000| $67.000| $100.000| $106.000 | $115.000
Fonseca, Barrancas → Anas Mai| $59.000| $66.000| $104.000| $110.000 | $125.000
San Juan, Villanueva, El Molino → Anas Mai| $71.000| $84.000| $124.000| $133.000 | $143.000
Incluye: almuerzo tipo asado, entrada con piscinas, transporte ida y vuelta.

TARIFAS PROMOCIONALES (no aplican en temporada alta)
Pasadía sin transporte: Cat A $21.500 | Cat B $24.000
Con transporte desde municipios:
  Maicao: Cat A $40.000 | Cat B $46.000
  Manaure/Uribia: Cat A $45.000 | Cat B $52.000
  Fonseca/Barrancas: Cat A $44.000 | Cat B $51.000
  San Juan/Villanueva/El Molino: Cat A $56.000 | Cat B $69.000

TEMPORADA ALTA (se cobra tarifa plena, no aplican promociones)
  • Semana Santa: 29 de marzo al 5 de abril
  • 15 de junio al 20 de julio
  • 20 de noviembre al 20 de enero

NORMAS
  • No se permite ingreso de animales/mascotas.
  • No se permite consumo de alcohol o sustancias psicoactivas.
  • Comfaguajira se reserva el derecho de admisión.
  • El pasadía con transporte requiere reservación previa; presentarse 30 min antes.
  • Pago anticipado en sedes de atención. Servicio sujeto a disponibilidad.
"""),

    art(
        title='Anas Mai — alquiler de espacios y servicios de eventos 2026',
        category='recreacion-anas-mai',
        content="""\
ALQUILER DE ESPACIOS — CENTRO SOCIO CULTURAL Y RECREATIVO ANAS MAI
Tarifas incluyen IVA 19%

INCLUYE: Video beam, 1 botellón de agua cada 40 personas, café, aromática, sillas,
planta eléctrica, soporte técnico, wifi básico, aire acondicionado, vigilancia,
tablero acrílico y 2 marcadores, oferta de cafetería/restaurante.
NO incluyen: computador portátil, servicio de sonido.

MEDIO DÍA — 4 HORAS
Espacio            | Cat A   | Cat B   | Cat C     | Emp.Afil. | Particular
Auditorio          | $478.400| $549.000| $866.000  | $996.000  | $1.127.000
Salón N.º 2        | $207.000| $238.000| $378.000  | $423.000  | $446.000
Salón N.º 4        | $318.300| $365.000| $574.000  | $652.000  | $750.000
Salón N.º 5        | $119.500| $135.000| $214.000  | $240.000  | $273.000
Salón N.º 6 (100%) | $634.000| $744.000| $1.035.000| $1.164.000| $1.294.000
Salón N.º 6 (50%)  | $317.000| $372.000| $517.000  | $582.000  | $647.000
Área social        | $475.700| $539.000| $851.000  | $986.000  | $1.115.000
Alquiler Restaurante| $326.300| $385.000| $593.000  | $670.000  | $771.000
Salón de Cristal   | $332.600| $382.000| $602.000  | $692.000  | $784.000
Alquiler Terraza   | $181.200| $202.000| $324.000  | $356.000  | $409.000

UN DÍA — 8 HORAS
Espacio            | Cat A   | Cat B     | Cat C     | Emp.Afil.   | Particular
Auditorio          | $957.000| $1.099.000| $1.732.000| $1.991.000  | $2.255.000
Salón N.º 2        | $414.000| $476.000  | $755.000  | $846.000    | $892.000
Salón N.º 4        | $636.000| $730.000  | $1.148.000| $1.304.000  | $1.500.000
Salón N.º 5        | $239.000| $270.000  | $429.000  | $480.000    | $545.000
Salón N.º 6 (100%) |$1.268.000|$1.488.000| $2.070.000| $2.329.000 | $2.588.000
Salón N.º 6 (50%)  | $634.000| $744.000  | $1.035.000| $1.164.000  | $1.294.000
Área social        | $951.000| $1.077.000| $1.701.000| $1.972.000  | $2.230.000
Alquiler Restaurante| $652.000| $770.000  | $1.187.000| $1.341.000 | $1.541.000
Salón de Cristal   | $666.000| $765.000  | $1.204.000| $1.384.000  | $1.567.000
Alquiler Terraza   | $362.000| $404.000  | $647.000  | $712.000    | $819.000

MONTAJE Y DESMONTAJE DE EVENTOS
Tiempo  | Tarifa plena  | Tarifa nocturna
2 horas | $297.000      | $346.680
4 horas | $595.080      | $693.360
6 horas | $892.080      | $1.040.040
8 horas | $1.189.080    | $1.386.720
Inicio horario nocturno: 7:00 p.m.

CANCELACIONES DE RESERVA
  • Antes de 60 días: descuento del 15%
  • Entre 59 y 31 días: descuento del 25%
  • Entre 30 y 15 días: descuento del 50%
  • 14 días o menos: sin devolución del anticipo

TARIFAS PARA EVENTOS — ENSERES
Concepto                           | Tarifa
Mesas vestidas (redondas/rect.)    | $32.400
Mantel y sobremantel adicional     | $15.200
Mantel                             | $9.700
Sobremantel                        | $5.400
Sillas vestidas con lazo           | $8.700
Sillas Tifany                      | $10.800
Meseros por eventos (1 c/20 pers.) | $150.000

COFFEE BREAK SEGÚN CAPACIDAD
  1-40 personas:   1 termo café, 1 termo aromática, 1 dispensador agua
  1-80 personas:   2 termos café, 2 termos aromática, 1 dispensador agua
  1-120 personas:  3 termos café, 3 termos aromática, 1 dispensador agua
  1-350 personas:  1 greca para café y aromática, 3 dispensadores
  1-500 personas:  2 grecas para café y aromática, 3 dispensadores

Servicios adicionales coffee break:
  Café en termo para 20 pax:        $14.000
  Aromática en termo para 20 pax:   $14.000
  Greca de café y aromática:        $94.000
"""),

    # =========================================================
    # RECREACIÓN — MAZIRUMA
    # =========================================================
    art(
        title='Maziruma — pasadía, entrada y alquiler de espacios 2026',
        category='recreacion-maziruma',
        content="""\
CENTRO RECREACIONAL Y VACACIONAL MAZIRUMA — DIBULLA
Tarifas incluyen IVA 19%

ENTRADA AL CENTRO
Tipo          | Cat A | Cat B  | Cat C   | Emp.Afil.| Particular
Entrada       | $650  | $3.250 | $11.900 | $13.000  | $18.000
Incluye: piscinas, parque infantil, canchas deportivas (sin implementos), parqueadero vigilado.

PASADÍA MAZIRUMA SIN TRANSPORTE
Cat A: $36.650 | Cat B: $39.250 | Cat C: $48.000 | Emp. Afil.: $49.000 | Particular: $54.300
Incluye: almuerzo ejecutivo, entrada con piscinas.

PASADÍA MAZIRUMA CON TRANSPORTE
Ruta                                 | Cat A   | Cat B   | Cat C    | Emp.Afil.| Particular
Desde Riohacha                       | $55.200 | $62.600 | $89.100  | $94.400  | $101.800
Desde Maicao                         | $67.300 | $76.900 | $136.600 | $146.200 | $155.800
Desde Manaure, Uribia                | $78.000 | $87.600 | $147.400 | $157.000 | $166.600
Desde Fonseca, Barrancas             | $72.600 | $82.200 | $142.000 | $151.600 | $171.900
Desde San Juan, El Molino, Villanueva| $84.400 | $96.200 | $153.900 | $165.600 | $183.800

TARIFAS PROMOCIONALES (no aplican en temporada alta)
Sin transporte: Cat A $21.700 | Cat B $24.100
Con transporte:
  Desde Riohacha: Cat A $38.000 | Cat B $45.000
  Desde Maicao: Cat A $49.000 | Cat B $58.000
  Desde Manaure/Uribia: Cat A $59.000 | Cat B $68.000
  Desde Fonseca/Barrancas: Cat A $54.000 | Cat B $63.000
  Desde San Juan/El Molino/Villanueva: Cat A $65.000 | Cat B $76.000

TEMPORADA ALTA (tarifa plena, sin promociones)
  • Semana Santa: 29 de marzo al 5 de abril
  • 15 de junio al 20 de julio
  • 20 de noviembre al 20 de enero

HORARIO PISCINA MAZIRUMA (Pasadía)
  Martes, domingo y festivos: 9:00 a.m. – 6:00 p.m.

ALQUILER DE ESPACIOS — MAZIRUMA
Espacio      | Cat A   | Cat B   | Cat C   | Emp.Afil.| Particular
Auditorio    | $207.000| $240.000| $433.000| $478.000 | $498.000
Salón 1      | $78.000 | $85.000 | $129.000| $161.000 | $170.000
Salón 2      | $63.000 | $68.000 | $95.000 | $117.000 | $127.000
Salón 3      | $108.000| $118.000| $165.000| $203.000 | $218.000
Incluye: IVA, aromática, café y agua.

ALQUILER DE HAMACAS (por día)
Cat A: $10.000 | Cat B: $10.800 | Cat C: $11.900 | Emp. Afil.: $12.500 | Particular: $13.000

TARIFAS PARA EVENTOS — MAZIRUMA (iguales a Anas Mai)
Meseros (1 por cada 20 personas): $150.000
Mesas vestidas: $32.400 | Mantel y sobremantel: $15.200 | Sillas vestidas con lazo: $8.700
Sillas Tifany: $10.800 | Mantel: $9.700 | Sobremantel: $5.400

FORMAS DE PAGO
Efectivo, tarjeta débito/crédito, crédito empresarial (grupos), consignación.
Cuenta Bancolombia: 52600004229 (Anas Mai – Maziruma)
"""),

    art(
        title='Maziruma — alojamiento en temporada alta y baja 2026',
        category='recreacion-maziruma',
        content="""\
PROGRAMA DE ALOJAMIENTO — MAZIRUMA (DIBULLA)

CHECK-IN: a partir de las 3:00 p.m. (puede usar el centro recreativo antes)
CHECK-OUT: hasta las 12:00 m. (multa de $10.000 por persona si se pasa)
HORARIO PISCINA PARA HUÉSPEDES: martes a domingo 10:00 a.m. – 9:00 p.m.
Niños menores de 5 años no pagan alojamiento (cancelan seguro hotelero por noche).

═══════════════════════════════════════════════════
TEMPORADA ALTA — TARIFAS POR PERSONA/NOCHE
═══════════════════════════════════════════════════

CABAÑAS — PLAN EUROPEO (solo alojamiento, sin comidas)
Acomod.    | Cat A   | Cat B   | Cat C    | Emp.Afil. | Particular | Comisionable
Triple     | $43.600 | $51.900 | $110.200 | $124.200  | $143.200   | $110.600
Cuádruple  | $33.200 | $39.500 | $83.200  | $93.700   | $107.950   | $83.500
Quíntuple  | $27.000 | $32.000 | $67.000  | $75.400   | $86.800    | $67.200

CABAÑAS — PLAN CONTINENTAL (alojamiento + desayuno americano)
Acomod.    | Cat A   | Cat B   | Cat C    | Emp.Afil. | Particular | Comisionable
Triple     | $62.100 | $70.400 | $128.700 | $142.700  | $161.700   | $129.700
Cuádruple  | $51.700 | $58.000 | $101.700 | $112.200  | $126.500   | $102.700
Quíntuple  | $45.500 | $50.500 | $85.500  | $93.900   | $105.300   | $86.500

CABAÑAS — PLAN AMERICANO MODIFICADO (alojamiento + desayuno + almuerzo)
Acomod.    | Cat A   | Cat B   | Cat C    | Emp.Afil. | Particular | Comisionable
Triple     | $98.100 | $106.400| $164.700 | $178.700  | $197.700   | $165.700
Cuádruple  | $87.700 | $94.000 | $137.700 | $148.200  | $162.500   | $138.700
Quíntuple  | $81.500 | $86.500 | $121.500 | $129.900  | $141.300   | $122.500

CABAÑAS — PLAN AMERICANO (alojamiento + desayuno + almuerzo + cena)
Acomod.    | Cat A    | Cat B    | Cat C    | Emp.Afil. | Particular | Comisionable
Triple     | $121.600 | $129.900 | $188.200 | $202.200  | $221.200   | $189.200
Cuádruple  | $111.200 | $117.500 | $161.200 | $171.700  | $186.000   | $162.200
Quíntuple  | $105.000 | $110.000 | $145.000 | $153.400  | $164.800   | $146.000

HABITACIONES TIPO HOTEL — PLAN EUROPEO
Acomod.    | Cat A   | Cat B   | Cat C    | Emp.Afil. | Particular | Comisionable
Sencilla   | $81.200 | $91.200 | $180.600 | $198.200  | $223.200   | $181.600
Doble      | $50.700 | $57.700 | $109.650 | $120.700  | $135.200   | $110.650
Triple     | $43.900 | $51.200 | $98.400  | $108.200  | $121.600   | $99.400
Cuádruple  | $38.500 | $45.200 | $85.400  | $94.000   | $104.700   | $86.400

HABITACIONES TIPO HOTEL — PLAN CONTINENTAL
Acomod.    | Cat A   | Cat B   | Cat C    | Emp.Afil. | Particular | Comisionable
Sencilla   | $99.700 | $109.700| $199.100 | $216.700  | $241.700   | $200.100
Doble      | $69.200 | $76.200 | $128.200 | $139.200  | $153.700   | $129.200
Triple     | $62.400 | $69.700 | $116.900 | $126.700  | $140.100   | $117.900
Cuádruple  | $57.000 | $63.700 | $103.900 | $112.500  | $123.200   | $104.900

HABITACIONES TIPO HOTEL — PLAN AMERICANO MODIFICADO
Acomod.    | Cat A    | Cat B    | Cat C    | Emp.Afil. | Particular | Comisionable
Sencilla   | $135.700 | $145.700 | $235.100 | $252.700  | $277.700   | $236.100
Doble      | $105.200 | $112.200 | $164.200 | $175.200  | $189.700   | $165.200
Triple     | $98.400  | $105.700 | $152.900 | $162.700  | $176.100   | $153.900
Cuádruple  | $93.000  | $99.700  | $139.900 | $148.500  | $159.200   | $140.900

HABITACIONES TIPO HOTEL — PLAN AMERICANO
Acomod.    | Cat A    | Cat B    | Cat C    | Emp.Afil. | Particular | Comisionable
Sencilla   | $159.200 | $169.200 | $258.600 | $276.200  | $301.200   | $259.600
Doble      | $128.700 | $135.700 | $187.700 | $198.700  | $213.200   | $188.700
Triple     | $121.900 | $129.200 | $176.400 | $186.200  | $199.600   | $177.400
Cuádruple  | $116.500 | $123.200 | $163.400 | $172.000  | $182.700   | $164.400

APARTAMENTOS — PLAN EUROPEO
Acomod.    | Cat A   | Cat B   | Cat C   | Emp.Afil. | Particular | Comisionable
Cuádruple  | $43.200 | $52.000 | $98.000 | $126.500  | $144.500   | $99.000
Quíntuple  | $35.000 | $42.000 | $80.600 | $101.200  | $115.600   | $81.600
Séxtuple   | $29.600 | $35.400 | $67.600 | $86.600   | $98.600    | $67.700
Séptuple   | $25.700 | $30.700 | $58.200 | $74.500   | $84.800    | $58.400
Óctuple    | $22.700 | $27.100 | $51.200 | $65.500   | $74.500    | $51.400

APARTAMENTOS — PLAN CONTINENTAL
Acomod.    | Cat A   | Cat B   | Cat C    | Emp.Afil. | Particular | Comisionable
Cuádruple  | $61.700 | $70.500 | $116.500 | $145.000  | $163.000   | $117.500
Quíntuple  | $53.500 | $60.500 | $99.100  | $119.700  | $134.100   | $100.100
Séxtuple   | $48.100 | $53.900 | $86.100  | $105.100  | $117.100   | $87.100
Séptuple   | $44.200 | $49.200 | $76.700  | $93.000   | $103.300   | $77.700
Óctuple    | $41.200 | $45.600 | $69.700  | $84.000   | $93.000    | $70.700

APARTAMENTOS — PLAN AMERICANO MODIFICADO
Acomod.    | Cat A   | Cat B   | Cat C    | Emp.Afil. | Particular | Comisionable
Cuádruple  | $97.700 | $106.500| $152.500 | $181.000  | $199.000   | $153.500
Quíntuple  | $89.500 | $96.500 | $135.100 | $155.700  | $170.100   | $136.100
Séxtuple   | $84.100 | $89.900 | $122.100 | $141.100  | $153.100   | $123.100
Séptuple   | $80.200 | $85.200 | $112.700 | $129.000  | $139.300   | $113.700
Óctuple    | $77.200 | $81.600 | $105.700 | $120.000  | $129.000   | $106.700

APARTAMENTOS — PLAN AMERICANO
Acomod.    | Cat A    | Cat B    | Cat C    | Emp.Afil. | Particular | Comisionable
Cuádruple  | $121.200 | $130.000 | $176.000 | $204.500  | $222.500   | $177.000
Quíntuple  | $113.000 | $120.000 | $158.600 | $179.200  | $193.600   | $159.600
Séxtuple   | $107.600 | $113.400 | $145.600 | $164.600  | $176.600   | $146.600
Séptuple   | $103.700 | $108.700 | $136.200 | $152.500  | $162.800   | $137.200
Óctuple    | $100.700 | $105.100 | $129.200 | $143.500  | $152.500   | $130.200

GLAMPING KOGUI — PLAN EUROPEO
Acomod. Doble | Cat A: $24.000 | Cat B: $31.000 | Cat C: $74.000 | Emp.Afil.: $101.000 | Particular: $118.000 | Comisionable: $75.000
GLAMPING KOGUI — PLAN CONTINENTAL
Acomod. Doble | Cat A: $42.500 | Cat B: $49.500 | Cat C: $92.500 | Emp.Afil.: $119.500 | Particular: $136.500 | Comisionable: $93.500
GLAMPING KOGUI — PLAN AMERICANO MODIFICADO
Acomod. Doble | Cat A: $78.500 | Cat B: $85.500 | Cat C: $128.500 | Emp.Afil.: $155.500 | Particular: $172.500 | Comisionable: $129.500
GLAMPING KOGUI — PLAN AMERICANO
Acomod. Doble | Cat A: $114.500 | Cat B: $121.500 | Cat C: $164.500 | Emp.Afil.: $191.500 | Particular: $208.500 | Comisionable: $165.500

GLAMPING HIPOGEO — PLAN EUROPEO
Cuádruple: Cat A $15.000 | Cat B $25.000 | Cat C $46.250 | Emp.Afil. $59.750 | Particular $68.000
Quíntuple: Cat A $12.000 | Cat B $20.000 | Cat C $37.000 | Emp.Afil. $47.800 | Particular $54.400
Séxtuple:  Cat A $10.000 | Cat B $16.000 | Cat C $31.000 | Emp.Afil. $39.833 | Particular $45.333
GLAMPING HIPOGEO — PLAN CONTINENTAL
Cuádruple: Cat A $33.500 | Cat B $43.500 | Cat C $64.750 | Emp.Afil. $78.250 | Particular $86.500
Quíntuple: Cat A $30.500 | Cat B $38.500 | Cat C $55.500 | Emp.Afil. $66.300 | Particular $72.900
Séxtuple:  Cat A $28.500 | Cat B $34.500 | Cat C $49.500 | Emp.Afil. $58.400 | Particular $63.800
GLAMPING HIPOGEO — PLAN AMERICANO MODIFICADO
Cuádruple: Cat A $74.500 | Cat B $87.500 | Cat C $116.500 | Emp.Afil. $134.200 | Particular $145.200
Quíntuple: Cat A $70.000 | Cat B $80.000 | Cat C $101.000 | Emp.Afil. $114.000 | Particular $123.000
Séxtuple:  Cat A $67.000 | Cat B $75.000 | Cat C $92.000  | Emp.Afil. $102.000 | Particular $109.000
GLAMPING HIPOGEO — PLAN AMERICANO
Cuádruple: Cat A $110.500 | Cat B $123.500 | Cat C $152.500 | Emp.Afil. $170.200 | Particular $181.200
Quíntuple: Cat A $106.000 | Cat B $116.000 | Cat C $137.000 | Emp.Afil. $150.000 | Particular $159.000
Séxtuple:  Cat A $103.000 | Cat B $111.000 | Cat C $128.000 | Emp.Afil. $138.000 | Particular $145.000

═══════════════════════════════════════════════════
TEMPORADA BAJA / PROMOCIONAL — Solo Cat A y B
═══════════════════════════════════════════════════
(mismos tipos de plan, solo Cat A y Cat B)

CABAÑAS — Plan Europeo: Triple Cat A $28.500 / Cat B $37.500 | Cuádruple A $22.000 / B $28.700 | Quíntuple A $18.000 / B $23.400
CABAÑAS — Plan Continental: Triple A $40.200 / B $49.200 | Cuádruple A $33.700 / B $40.400 | Quíntuple A $29.700 / B $35.100
CABAÑAS — Plan Americano Modificado: Triple A $59.600 / B $68.600 | Cuádruple A $53.100 / B $59.800 | Quíntuple A $49.100 / B $54.500
CABAÑAS — Plan Americano: Triple A $71.300 / B $80.300 | Cuádruple A $64.800 / B $71.500 | Quíntuple A $60.800 / B $66.200

HAB. HOTEL — Plan Europeo: Sencilla A $45.600 / B $60.600 | Doble A $26.200 / B $35.200 | Triple A $23.400 / B $31.500 | Cuádruple A $20.300 / B $27.200
HAB. HOTEL — Plan Continental: Sencilla A $57.300 / B $72.300 | Doble A $37.900 / B $46.900 | Triple A $35.100 / B $43.200 | Cuádruple A $32.000 / B $38.900
HAB. HOTEL — Plan Am. Modificado: Sencilla A $76.700 / B $91.700 | Doble A $57.300 / B $66.300 | Triple A $54.500 / B $62.600 | Cuádruple A $51.400 / B $58.300
HAB. HOTEL — Plan Americano: Sencilla A $88.400 / B $103.400 | Doble A $69.000 / B $78.000 | Triple A $66.200 / B $74.300 | Cuádruple A $63.100 / B $70.000

APTOS — Plan Europeo: Cuádruple A $25.700 / B $34.200 | Quíntuple A $21.000 / B $27.800 | Séxtuple A $17.900 / B $23.500 | Séptuple A $15.600 / B $20.500 | Óctuple A $13.900 / B $18.200
APTOS — Plan Continental: Cuádruple A $37.400 / B $45.900 | Quíntuple A $32.700 / B $39.500 | Séxtuple A $29.600 / B $35.200 | Séptuple A $27.300 / B $32.200 | Óctuple A $25.600 / B $29.900
APTOS — Plan Am. Modificado: Cuádruple A $56.900 / B $65.400 | Quíntuple A $52.200 / B $59.000 | Séxtuple A $49.100 / B $54.700 | Séptuple A $46.800 / B $51.700 | Óctuple A $45.100 / B $49.400
APTOS — Plan Americano: Cuádruple A $68.600 / B $77.100 | Quíntuple A $63.900 / B $70.700 | Séxtuple A $60.800 / B $66.400 | Séptuple A $58.500 / B $63.400 | Óctuple A $56.800 / B $61.100

GLAMPING KOGUI TEMP. BAJA:
  Europeo Doble: A $13.000 / B $24.200
  Continental Doble: A $24.700 / B $35.900
  Am. Modificado Doble: A $44.200 / B $55.400
  Americano Doble: A $63.700 / B $74.900

GLAMPING HIPOGEO TEMP. BAJA:
  Europeo: Cuádruple A $8.200/B $15.200 | Quíntuple A $6.600/B $12.100 | Séxtuple A $5.500/B $10.100
  Continental: Cuádruple A $19.900/B $26.900 | Quíntuple A $18.300/B $23.800 | Séxtuple A $17.200/B $21.800
  Am. Modificado: Cuádruple A $39.400/B $46.400 | Quíntuple A $37.800/B $43.300 | Séxtuple A $36.700/B $41.300
  Americano: Cuádruple A $49.000/B $53.000 | Quíntuple A $48.000/B $51.500 | Séxtuple A $47.000/B $50.500

Tarifas comisionables aplican para alianzas con agencias de viajes.
"""),

    # =========================================================
    # RECREACIÓN — POLIDEPORTIVO HATONUEVO
    # =========================================================
    art(
        title='Polideportivo Hatonuevo — pasadía y tarifas 2026',
        category='recreacion',
        content="""\
PROGRAMA PASADÍA — POLIDEPORTIVO HATONUEVO

ENTRADA AL CENTRO
Tipo   | Cat A | Cat B  | Cat C  | Emp.Afil.| Particular
Entrada| $300  | $1.300 | $4.700 | $5.200   | $7.400
Incluye: piscinas, parque infantil, canchas deportivas (sin implementos), parqueadero vigilado.

PASADÍA SIN TRANSPORTE (comida + entrada)
Cat A: $25.600 | Cat B: $30.200 | Cat C: $40.800 | Emp. Afil.: $41.300 | Particular: $43.500
Incluye: almuerzo ejecutivo, entrada con derecho a piscinas.

PASADÍA CON TRANSPORTE DESDE MUNICIPIOS
Ruta                                  | Cat A   | Cat B   | Cat C    | Emp.Afil.| Particular
Desde Riohacha                        | $62.800 | $71.200 | $101.400 | $107.000 | $116.000
Desde Maicao                          | $49.900 | $57.000 | $101.300 | $108.000 | $116.000
Desde Manaure, Uribia                 | $74.100 | $83.300 | $140.100 | $149.000 | $158.000
Desde Fonseca, Barrancas              | $41.500 | $47.000 | $81.200  | $87.000  | $98.000
Desde San Juan, El Molino, Villanueva | $50.000 | $57.000 | $91.100  | $98.000  | $109.000

PASADÍA PROMOCIONAL SIN TRANSPORTE
Cat A: $18.900 | Cat B: $20.000
(piscina adultos, piscina niños, tobogán, snack cafetería, helados 9 a.m. – 6 p.m., vigilancia)

PASADÍA PROMOCIONAL CON TRANSPORTE
Ruta                                  | Cat A   | Cat B
Desde Riohacha                        | $45.900 | $54.300
Desde Maicao                          | $38.800 | $45.900
Desde Manaure, Uribia                 | $59.900 | $69.100
Desde Fonseca, Barrancas              | $33.000 | $38.500
Desde San Juan, El Molino, Villanueva | $41.100 | $48.100

TEMPORADA ALTA (tarifa plena)
  • Semana Santa: 29 de marzo al 5 de abril (el tarifario indica también "29 de mayo" — verificar)
  • 15 de junio al 20 de julio
  • 20 de noviembre al 20 de enero

El pasadía con transporte requiere reservación previa; presentarse 30 min antes.
Transporte sujeto a disponibilidad; si no hay bus propio se cotiza con tercero.
"""),

    # =========================================================
    # TURISMO SOCIAL
    # =========================================================
    art(
        title='Turismo Social — Cabo de la Vela 2026',
        category='turismo',
        content="""\
TURISMO SOCIAL — PLANES CABO DE LA VELA 2026
Tarifas sujetas a cambio en temporada alta y disponibilidad.

1 DÍA (PASADÍA) — MÍN. 4 PERSONAS — DESDE RIOHACHA (camioneta)
Incluye: acompañamiento, caminata al Faro, Pilón de Azúcar, Salinas de Manaure, 1 almuerzo
con pescado, transporte Riohacha–Cabo–Riohacha, seguro de viaje.
Salida: 5:00 a.m. | Regreso: ~3:00 p.m. | Duración por trayecto: ~4 horas
Cat A: $145.000 | Cat B: $173.000 | Cat C: $289.000 | Emp. Afil.: $305.000 | Particular: $314.600 | Comisionable: $297.000

1 DÍA (PASADÍA) — 4 PERSONAS — DESDE MAZIRUMA (camioneta)
Salida: 5:30 a.m. | Regreso: ~3:00 p.m.
Cat A: $176.000 | Cat B: $212.000 | Cat C: $353.000 | Emp. Afil.: $363.000 | Particular: $385.000 | Comisionable: $358.000

1 DÍA (PASADÍA) — MÍN. 20 PERSONAS — DESDE MAZIRUMA (bus)
Salida: 5:30 a.m. | Regreso: ~3:00 p.m.
Cat A: $185.000 | Cat B: $222.000 | Cat C: $370.700 | Emp. Afil.: $387.000 | Particular: $414.200 | Comisionable: $379.000

1 DÍA (PASADÍA) — GRUPOs MÍN. 20 PERSONAS — DESDE RIOHACHA (bus)
Salida: 5:30 a.m. | Regreso: ~3:00 p.m.
Cat A: $157.000 | Cat B: $188.000 | Cat C: $314.000 | Emp. Afil.: $334.000 | Particular: $357.000 | Comisionable: $324.000

1 DÍA SIN TRANSPORTE — GRUPOs MÍN. 20 PERSONAS
Incluye: acompañamiento, Faro, Pilón de Azúcar, Salinas, 1 almuerzo. Sin transporte.
Cat A: $37.000 | Cat B: $44.000 | Cat C: $73.600 | Emp. Afil.: $80.600 | Particular: $84.000 | Comisionable: $77.000

SOLO TRANSPORTE GRUPOS MÍN. 20 PERSONAS (oferta empresarial — bus hasta 33 pax)
Ruta: Riohacha–Manaure–Cabo–Riohacha
Empresa afiliada: $4.603.000 | Particular: $4.831.800 | Comisionable: $4.509.000

2 DÍAS 1 NOCHE — MÍN. 4 PERSONAS (camionetas, desde Riohacha)
Incluye: acompañamiento, Faro, Pilón de Azúcar, Salinas, 2 almuerzos, 1 cena, 1 desayuno,
transporte Riohacha–Cabo–Riohacha, seguro de viaje, alojamiento 1 noche en cabaña con baño interno.
Salida: 7:00 a.m. | Regreso al día siguiente: 2:00 p.m.
Nota: cabañas wayuu cuentan con cama, abanico y baño privado (sin toallas ni elementos de aseo).
Cat A: $341.000 | Cat B: $409.000 | Cat C: $681.800 | Emp. Afil.: $701.000 | Particular: $716.800 | Comisionable: $691.000

2 DÍAS 1 NOCHE SIN TRANSPORTE — GRUPOs MÍN. 20 PERSONAS — OPC. 1 (CHINCHORRO)
Incluye: acompañamiento, Faro, Pilón de Azúcar, Salinas, 2 almuerzos, 1 cena, 1 desayuno, dormida en chinchorro.
Cat A: $170.000 | Cat B: $203.000 | Cat C: $339.100 | Emp. Afil.: $369.000 | Particular: $383.000 | Comisionable: $354.000

2 DÍAS 1 NOCHE SIN TRANSPORTE — GRUPOs MÍN. 20 PERSONAS — OPC. 2 (CABAÑA)
Incluye: acompañamiento, Faro, Pilón de Azúcar, Salinas, 2 almuerzos, 1 cena, 1 desayuno, dormida en cabaña.
Cat A: $172.000 | Cat B: $206.000 | Cat C: $343.400 | Emp. Afil.: $358.000 | Particular: $370.800 | Comisionable: $351.000

2 DÍAS 1 NOCHE CON TRANSPORTE — GRUPOs MÍN. 20 PERSONAS (bus, desde Riohacha)
Incluye: acompañamiento, Faro, Pilón de Azúcar, Salinas, 2 almuerzos, 1 cena, 1 desayuno,
transporte Riohacha–Cabo–Riohacha en bus, seguro de viaje, 1 noche en cabaña.
Cat A: $271.000 | Cat B: $325.000 | Cat C: $542.300 | Emp. Afil.: $595.000 | Particular: $625.000 | Comisionable: $569.000
"""),

    art(
        title='Turismo Social — Tardes de Ranchería y Santuario Flora y Fauna 2026',
        category='turismo',
        content="""\
TURISMO SOCIAL — TARDES DE RANCHERÍA WAYUU

Experiencia en Ranchería Iwouya, km 17 vía Valledupar.
Incluye: cóctel de bienvenida a base de Chirrinchi (bebida artesanal Wayuu), charla sobre
mitos y leyendas de la etnia, degustación del plato típico FRICHE, baile tradicional IONNA o
CHICHAMAYA. Hora de salida: 3:00 p.m. | Hora de regreso: 5:00 p.m.

CON TRANSPORTE — 4 PERSONAS (desde Riohacha, camioneta)
Cat A: $271.000 | Cat B: $325.000 | Cat C: $542.300 | Emp. Afil.: $595.000 | Particular: $625.000 | Comisionable: $569.000

CON TRANSPORTE — MÍN. 20 PERSONAS (desde Riohacha, buseta)
Cat A: $51.000 | Cat B: $65.000 | Cat C: $144.000 | Emp. Afil.: $150.000 | Particular: $159.200 | Comisionable: $147.000

SIN TRANSPORTE — MÍN. 20 PERSONAS (incluye guía y seguro de viaje)
Cat A: $42.000 | Cat B: $55.000 | Cat C: $121.000 | Emp. Afil.: $134.000 | Particular: $137.400 | Comisionable: $128.000

CON TRANSPORTE DESDE MAZIRUMA — 4 PERSONAS (camioneta)
Cat A: $29.000 | Cat B: $37.000 | Cat C: $82.000 | Emp. Afil.: $84.200 | Particular: $90.000 | Comisionable: $83.000

CON TRANSPORTE DESDE MAZIRUMA — MÍN. 20 PERSONAS (buseta)
Cat A: $84.000 | Cat B: $108.000 | Cat C: $240.900 | Emp. Afil.: $263.000 | Particular: $286.400 | Comisionable: $252.000

─────────────────────────────────────────────────────────────

TURISMO SOCIAL — SANTUARIO DE FLORA Y FAUNA (CAMARONES, ~20 min de Riohacha)
Caminata a la laguna, recorrido en canoa artesanal (~2 horas), avistamiento de
flamencos rosados (aves migratorias — no garantizadas). Playas turísticas disponibles.

4 PERSONAS — CON TRANSPORTE DESDE RIOHACHA (carro para 4)
Incluye: transporte Riohacha–Camarones–Riohacha, 1 almuerzo con pescado, paseo en canoa, seguro de viaje.
Cat A: $64.000 | Cat B: $82.000 | Cat C: $183.200 | Emp. Afil.: $205.000 | Particular: $226.500 | Comisionable: $194.000

MÍN. 20 PERSONAS — CON TRANSPORTE (buseta)
Cat A: $109.000 | Cat B: $131.000 | Cat C: $219.000 | Emp. Afil.: $225.000 | Particular: $233.900 | Comisionable: $222.000

MÍN. 20 PERSONAS — SIN TRANSPORTE (incluye almuerzo, guianza, canoa, seguro)
Cat A: $101.000 | Cat B: $121.000 | Cat C: $201.000 | Emp. Afil.: $207.000 | Particular: $218.000 | Comisionable: $204.000

4 PERSONAS — DESDE MAZIRUMA (carro para 4)
Cat A: $88.000 | Cat B: $106.000 | Cat C: $177.000 | Emp. Afil.: $195.000 | Particular: $207.100 | Comisionable: $186.000

MÍN. 20 PERSONAS — DESDE MAZIRUMA (bus)
Cat A: $103.000 | Cat B: $124.000 | Cat C: $206.400 | Emp. Afil.: $209.000 | Particular: $235.800 | Comisionable: $208.000
"""),

    art(
        title='Turismo Social — Tierra Guajira, Alta Guajira, Mayapo y Palomino 2026',
        category='turismo',
        content="""\
TURISMO SOCIAL — PLANES TIERRA GUAJIRA (5 Días, 4 Noches)

No incluyen tiquetes aéreos ni servicios no estipulados.
El hotel es convenido con el cliente; tarifas sujetas a disponibilidad hotelera.

OPCIÓN 1 — 5D/4N HOTEL RIOHACHA — 4 PERSONAS CON TRANSPORTE
Incluye: traslado aeropuerto–hotel–aeropuerto, alojamiento hotel Riohacha, alimentación completa,
transporte a destinos turísticos, City Tour Riohacha, Santuario Flora y Fauna (Flamencos),
Salinas de Manaure, Cabo de la Vela, Faro, Pilón de Azúcar, Tarde de Ranchería, seguros de viaje.
Cat C: — | Emp. Afil.: $2.545.000 | Particular: $2.403.800 | Comisionable: $2.310.000

OPCIÓN 1 — 5D/4N HOTEL RIOHACHA — MÍN. 20 PERSONAS CON TRANSPORTE
Mismo itinerario + acompañamiento permanente y guianza.
Cat C: — | Emp. Afil.: $2.000.000 | Particular: $1.932.400 | Comisionable: $1.840.000

OPCIÓN 1 — 5D/4N HOTEL RIOHACHA — MÍN. 20 PERSONAS SIN TRANSPORTE
Emp. Afil.: $1.411.000 | Particular: $1.426.500 | Comisionable: $1.330.000

OPCIÓN 2 — 5D/3N HOTEL + 1N CABO DE LA VELA — 4 PERSONAS
Incluye: traslado aeropuerto, alojamiento 3 noches hotel Riohacha (desayunos y cena),
1 noche en Cabo de la Vela (alimentación completa), transporte a destinos, City Tour,
Flamencos, Salinas, Cabo, Faro, Pilón, Tarde de Ranchería, seguros de viaje.
Emp. Afil.: $2.030.000 | Particular: $2.065.800 | Comisionable: $1.920.000

OPCIÓN 2 — 5D/3N+1N CABO — MÍN. 20 PERSONAS CON TRANSPORTE
Emp. Afil.: $1.724.000 | Particular: $1.807.000 | Comisionable: $1.650.000

OPCIÓN 2 — 5D/3N+1N CABO — MÍN. 20 PERSONAS SIN TRANSPORTE
Emp. Afil.: $1.258.000 | Particular: $1.350.000 | Comisionable: $1.220.000

─────────────────────────────────────────────────────────────

TOUR ALTA GUAJIRA — MÍN. 20 PERSONAS (solo Cat C, Emp. Afil. y Particular)
4 noches: 2 en Riohacha (desayunos y cenas), 1 en Cabo de la Vela (todas las comidas),
1 en Punta Gallinas (todas las comidas). Recorridos: Salinas de Manaure, Faro, Pilón de Azúcar,
Dunas de Taroa, Bahía Honda, Portete, etc. Tarde de Ranchería, avistamiento aves en Camarones.
Transfer aeropuerto, traslados en camionetas, seguro de viaje.
Emp. Afil.: $1.137.000 | Particular: $1.180.200 | Comisionable: $1.160.000

─────────────────────────────────────────────────────────────

PLANES A MAYAPO

Plan Vuelve a Mayapo — por persona
Incluye: michelada de bienvenida, almuerzo con bebida, disfrute de instalaciones.
Cat A: $64.000 | Cat B: $76.000 | Cat C: $127.000 | Emp. Afil.: $144.000 | Particular: $149.800 | Comisionable: $136.000

Tour Mayapo — 4 Personas (camioneta desde Riohacha, ~30 min)
Incluye: transporte, disfrute de playa y brisa, almuerzo típico, seguro de viaje.
Cat A: $56.000 | Cat B: $67.000 | Cat C: $112.400 | Emp. Afil.: $126.000 | Particular: $130.300 | Comisionable: $119.000

Tour Mayapo — Mín. 20 Personas con transporte (buseta)
Cat A: $36.000 | Cat B: $43.000 | Cat C: $72.000 | Emp. Afil.: $80.100 | Particular: $82.000 | Comisionable: $76.000

─────────────────────────────────────────────────────────────

PASADÍAS A PALOMINO
Salida: 7:00 a.m. | Llegada: 4:00 p.m. | Todo niño a partir de 3 años paga.

CON TRANSPORTE — MÍN. 20 PERSONAS (bus Riohacha–Palomino–Riohacha)
Incluye: transporte, acompañamiento, almuerzo ejecutivo, seguro médico.
Cat A: $72.000 | Cat B: $87.000 | Cat C: $144.500 | Emp. Afil.: $163.000 | Particular: $178.100 | Comisionable: $154.000

SIN TRANSPORTE — MÍN. 20 PERSONAS
Cat A: $49.000 | Cat B: $58.000 | Cat C: $97.000 | Emp. Afil.: $110.000 | Particular: $113.200 | Comisionable: $104.000

POR PERSONA SIN TRANSPORTE (almuerzo + disfrute de instalaciones)
Cat A: $55.000 | Cat B: $65.000 | Cat C: $109.000 | Emp. Afil.: $124.000 | Particular: $128.400 | Comisionable: $117.000

NOTA: En caso de no haber transporte propio, el servicio se cotiza con terceros.
"""),

    # =========================================================
    # RECREACIÓN DIRIGIDA
    # =========================================================
    art(
        title='Recreación Dirigida — tarifas y servicios 2026 (Riohacha)',
        category='recreacion-dirigida',
        content="""\
PROGRAMA RECREACIÓN DIRIGIDA 2026 — RIOHACHA
Tarifas incluyen IVA 19%

Servicio                 | Descripción / Condiciones                     | Cat A   | Cat B   | Cat C    | Emp.Afil.| Particular
PERSONAJE ANIMADO        | 3 h, máx. 60 niños/adultos. Incluye operador  | $63.000 | $72.000 | $115.700 | $135.000 | $144.000
                         | y atuendo. Requiere 8 días anticipación.       |         |         |          |          |
INFLABLE PARQUE SALTARÍN | 3 h, 5-12 años, máx. 400 niños (1-4/turno)   |         | $153.000| $182.800 | $271.700 | $293.000 | $315.000
                         | Incluye extensiones y equipo. Requiere luz 110v|         |         |          |          |
INFLABLE ESCALADOR       | 3 h, 5-12 años. SOLO disponible en Anas Mai   |         | $143.000| $163.000 | $269.400 | $294.000 | $319.000
INFLABLE SALTARÍN        | 3 h, 1-5 años, máx. 400 niños (1-4/turno)    |         | $83.000 | $106.600 | $235.600 | $266.000 | $292.000
TÍTERES TEMÁTICO         | 1 h, máx. 100 niños. Incluye teatrinos/títeres| $97.000 | $111.000| $186.300 | $202.000 | $219.000
MUÑECO ANIMADO           | 3 h (20 min trabajo/15 min descanso), máx. 50 | $72.000 | $83.000 | $141.000 | $156.000 | $168.000
SERVICIO DE SONIDO       | 4 h, hasta 200 personas, hasta 6 micrófonos   | $81.000 | $93.000 | $174.400 | $191.000 | $208.000
VACACIONES RECREATIVAS   | 4 días, 3 h/jornada, máx. 25 niños            | $71.000 | $85.000 | $173.000 | $190.000 | $208.000
MÁQUINA LANZA HUMO       | 3 h, 5 disparos de humo. Requiere 8 días ant. | $96.000 | $102.000| $128.400 | $141.000 | $155.000
SERVICIO RECREACIONISTA  | 3 h, máx. 50 niños/adultos. Incluye parlante  | $106.000| $112.000| $142.100 | $156.000 | $170.000
LUZ DE DISCOTECA         | 3 h, 1 luz, incluye operador. 8 días ant.     | $29.000 | $35.500 | $59.600  | $66.000  | $71.000
GLOBOFLEXIA PARA FIESTAS | 3 h, 50 niños, 100 unid. globos               | $67.000 | $77.000 | $119.000 | $130.000 | $142.000
PINTUCARITAS             | 3 h, 50 niños/adultos. Pinturas y pinceles     | $83.000 | $95.000 | $149.400 | $161.000 | $173.000
SERVICIO DE KARAOKE      | 2 h, máx. 60 personas. Incluye video beam     | $190.000| $201.000| $275.100 | $304.000 | $331.000
ZONA POLIMOTOR           | 3 h, máx. 50 niños. Incluye recreacionistas,  | $380.000| $484.000| $829.100 | $916.000 | $962.000
                         | piscina de pelotas, inflable, teatrino, etc.   |         |         |          |          |
DESAFÍO-MATCH RECREATIVO | 4 h, máx. 60, 4 pruebas físicas recreativas    |  —      |  —      |   —      |$1.424.000|$1.540.000
DÍA DEL NIÑO             | 3 h, máx. 400 niños. 2 muñecos, 1 inflable,  |  —      |  —      |   —      |$3.547.000|$3.706.000
                         | recreación dirigida, 100 bolsitas golosinas     |         |         |          |          |
SHOW TEATRAL TEMÁTICO    | 1 h, máx. 100 niños. Actores recreativos       | $390.000| $444.000|$1.066.000|$1.125.000|$1.183.000
FIESTA DE DISFRACES      | Máx. 60 niños. Personajes, inflables, concursos|  —      |  —      |   —      |$3.844.000|$4.210.000
BINGO RECREATIVO         | 3 h, 100 pax. 100 tablas, balotera, sonido    | $208.000| $219.000| $448.500 | $491.000 | $511.000
POOL PARTY (Anas Mai)    | 4 h, máx. 120 personas. Sonido, decoración    |  —      |  —      |   —      |$3.344.000|$3.542.000
CARNAVALITO (Anas Mai)   | 3 h, máx. 400 niños. Show, espuma, batalla    |  —      |  —      |   —      |$7.435.000|$8.112.000

NOTAS GENERALES
  • Para los servicios que requieren fluido eléctrico (110v), el cliente debe suministrarlo.
  • Confirmación mínima con 8 días de anticipación para la mayoría de servicios.
  • Para reservaciones de Inflable Parque Saltarín: mínimo 2 días de anticipación.
"""),

    art(
        title='Recreación Dirigida fuera de Riohacha — tarifas 2026',
        category='recreacion-dirigida',
        content="""\
RECREACIÓN DIRIGIDA FUERA DE RIOHACHA (por zonas del departamento)

ZONAS DE COBERTURA
  • Zona Norte:  Maicao, Manaure, Uribia y corregimientos
  • Zona Sur:    Villanueva, El Molino, San Juan del Cesar, Fonseca, Barrancas, Hatonuevo
  • Troncal del Caribe: Dibulla, Mingueo, Palomino y corregimientos

PRODUCTOS Y TARIFAS POR ZONA (Cat A y Cat B solamente)
Servicio                                  | Cat A   | Cat B
Personaje animado                         | $63.000 | $72.000
Muñeco animado                            | $73.000 | $84.000
Servicio de Recreacionista                | $107.000| $113.000
Karaoke recreativo                        | $191.000| $201.000
Títeres temático                          | $98.000 | $112.000
Globoflexia                               | $68.000 | $77.000
Pintucaritas                              | $84.000 | $96.000
Bingo recreativo                          | $208.000| $220.000
Jornadas de vacaciones recreativas (4 d.) | $72.000 | $86.000

NOTAS
  • No se oferta todo el portafolio en municipios, solo los listados.
  • Disponibilidad sujeta a programación; consultar con 5 días de anticipación.
  • Los servicios son exclusivos para afiliados Categoría A y B en estas zonas.
"""),

    # =========================================================
    # DEPORTES Y GIMNASIO
    # =========================================================
    art(
        title='Deportes — torneos, actividades, escuelas deportivas y cancha 2026',
        category='deportes',
        content="""\
PROGRAMA DEPORTES 2026

TORNEOS DEPORTIVOS (tarifa por grupo / equipo)
Servicio                               | Cat A   | Cat B   | Cat C     | Emp.Afil. | Particular
Torneo Fútbol 7 (Riohacha, Maicao, SJ) | $674.000| $842.000| $1.123.200| $1.303.000| $1.337.000
Torneo Fútbol 6                        | $719.000| $899.000| $1.198.400| $1.390.000| $1.426.000
Hexagonal Fútbol 6                     |    —    |    —    |    —      | $568.000  | $574.000
Hexagonal Fútbol 6 Social              | $14.000 | $16.500 | $19.000   |    —      |    —
Torneo de Rana                         | $32.000 | $43.000 | $62.400   | $66.000   | $67.000
Torneo Voleibol Empresarial            | $303.000| $422.000| $662.000  | $669.000  | $680.000
Torneo Tenis de Mesa                   | $70.000 | $86.000 | $121.000  | $133.000  | $139.000
Torneo de Dominó                       | $35.500 | $54.000 | $65.000   | $71.000   | $82.000
Ferias Deportivas (tarifa por grupo)   |    —    |    —    |    —      | $452.000  | $479.000

Incluye: inscripción por grupo, hidratación, juzgamiento, juegos deportivos inflables (solo Riohacha).

ALQUILER DE CANCHA SINTÉTICA ANAS MAI
Tipo       | Cat A   | Cat B   | Cat C   | Emp.Afil.| Particular
Cancha día (6am–6pm)   | $42.000 | $49.000 | $69.200 | $80.000  | $86.000
Cancha noche (6pm–11pm)| $51.000 | $57.000 | $78.000 | $89.000  | $96.000

ACTIVIDADES DEPORTIVAS
Servicio                                   | Cat A  | Cat B  | Cat C   | Emp.Afil.| Particular
Caminata ecológica                         | $4.300 | $6.500 | $9.700  | $10.300  | $10.800
Festival de natación                       | $38.000| $56.000| $67.000 | $73.000  | $84.000
Hidrogimnasia                              | $13.000| $19.400| $29.000 | $31.000  | $32.000
Rumbaterapia empresarial                   | $4.300 | $5.400 | $18.500 | $19.500  | $20.000
Maratón bailable Comfaguajira              | $7.500 | $12.000| $19.600 | $20.000  | $24.000
Juegos deportivos inflables                | $32.000| $48.000| $80.000 | $97.000  | $113.000
Pilates, stretching y relajación empresarial|$119.000|$133.000|$148.000| $160.000 | $177.000
Pausas activas (100% sub. Cat A y B)       | $0     | $0     | $2.200  | $3.200   | $4.300
Uso piscina/hora — práctica natación libre | $18.300| $22.600| $30.000 | $34.000  | $39.000
Instructor de natación                     | $22.000| $22.000| $22.500 | $22.700  | $27.000

ESCUELAS DEPORTIVAS (mensualidad)
Servicio                                    | Cat A  | Cat B  | Cat C  | Emp.Afil.| Particular
INSCRIPCIÓN + PÓLIZA (única)               | $38.000| $38.000| $38.000| $38.000  | $38.000
Escuela de Patinaje                         | $57.000| $64.000| $74.000| $74.000  | $83.000
Escuela Natación Menores (5-7 años)        | $44.000| $58.000| $91.000| $90.000  | $97.000
Escuela Natación Infantil (8-11 años)      | $46.000| $61.000| $96.000| $94.000  | $103.000
Escuela Natación Juvenil (12-16 años)      | $51.000| $64.000|$101.000| $99.000  | $108.000
Escuela de Ajedrez                          | $38.000| $49.000| $83.000| $83.000  | $91.000
Escuela de Fútbol                           | $33.000| $44.000| $75.000| $75.000  | $82.000

Nota: tarifas vacacionales de escuelas iguales a las ordinarias.

UNIFORMES ESCUELAS DEPORTIVAS
Servicio                                    | Cat A  | Cat B   | Cat C    | Emp.Afil.| Particular
Uniforme presentación escuelas deportivas   | $65.000| $91.000 | $142.600 | $143.000 | $163.000
Uniforme entrenamiento patinaje             | $59.000| $83.000 | $129.900 | $130.000 | $140.000
Uniforme entrenamiento natación             |$107.000|$149.000 | $150.000 | $150.000 | $161.000
Uniforme entrenamiento ajedrez              | $42.000| $60.000 | $92.800  | $93.000  | $105.000
Uniforme entrenamiento fútbol               | $46.000| $52.000 | $63.900  | $64.000  | $66.000
"""),

    art(
        title='Gimnasio Comfaguajira — tarifas y promociones 2026',
        category='deportes',
        content="""\
GIMNASIO COMFAGUAJIRA 2026
Tarifas incluyen IVA 19%

TARIFAS REGULARES
Servicio           | Cat A   | Cat B   | Cat C   | Empresa | Particular
Sesión Gimnasio    | $2.000  | $2.500  | $2.800  | $0      | $3.300
Mensualidad        | $30.000 | $38.000 | $66.000 | $75.000 | $80.000
Rumbaterapia       | $0      | $0      | $2.500  | $3.000  | $3.300
Pausas Activas     | $0      | $0      | $2.000  | $2.500  | $3.000

DESCUENTO 50% — Horario lunes a viernes 5am–8pm / sábados 6am–4pm
Servicio           | Cat A   | Cat B   | Cat C   | Particular
Sesiones           | $1.000  | $1.300  | $1.400  | $1.600
Mensualidades      | $15.000 | $19.000 | $33.000 | $40.000

ANUALIDAD (paga 6 meses, recibe 12) — Horario L-V 7am–4pm / sábados 7am–4pm
Cat A: $180.000 | Cat B: $228.000 | Cat C: $396.000 | Particular: $480.000

SEMESTRE (30% de descuento) — Cualquier horario
Cat A: $126.000 | Cat B: $159.600 | Cat C: $277.200 | Particular: $336.000

TRIMESTRE (20% de descuento) — Cualquier horario
Cat A: $72.000 | Cat B: $91.200 | Cat C: $158.400 | Particular: $192.000

8 MESES (paga 8, recibe 12) — Cualquier horario
Cat A: $240.000 | Cat B: $304.000 | Cat C: $528.000 | Particular: $640.000
"""),

    # =========================================================
    # ALIMENTOS Y BEBIDAS
    # =========================================================
    art(
        title='Alimentos y Bebidas — Restaurante Perla Mar Anas Mai 2026',
        category='alimentos-bebidas',
        content="""\
CARTA RESTAURANTE PERLA MAR — ANAS MAI 2026

ENTRADAS
Sopa de pollo: $13.000 | Sopa de verduras: $8.700 | Guineo y camarones: $36.200
Fritura de mariscos: $40.900 | Cóctel Riohachero: $32.400

ENSALADAS
Ensalada de pollo al horno y verduras frescas: $28.100 | Ensalada César: $29.700
Ensalada Guajira: $23.600 | Ensalada Veggie: $18.400

PLATOS FUERTES
Arroz de camarón guajiro y mariscos: $73.500 | Arroz Perla Mar: $55.700
Langostino y cremoso: $69.700 | Festival de mariscos: $85.400
Cazuela de mariscos: $75.600 | Pescado al grill: $57.800
Langostinos a la parmesana: $80.500 | Paella guajira: $63.200
Lomo asado al vino tinto: $43.200 | Baby beef: $45.400 | Filet mignon: $47.600
Pollo con verduras a la mantequilla: $35.700 | Pollo español: $41.100
Rollito francés: $48.600 | Pescado sierra: $53.000 | Pescado pargo x400 g: $68.100

PASTAS
Lasagna de chivo y queso azul: $43.200 | Veggie pesto: $26.000
Pastas Perlamar: $71.300 | Pastas de cítricos y pescado: $61.600

ADICIONALES
Pechuga de pollo al horno x150 g: $15.200 | Langostinos x120 g: $57.300
Lomo fino x120 g: $28.100 | Papas a la francesa x125 g: $8.700 | Patacones x200 g: $6.500

POSTRES
Flan de caramelo tradicional: $16.200 | Napoleon: $17.300 | Costron de coco: $17.300
Cremoso: $11.900

BEBIDAS (RESTAURANTE)
Limonada cerezada frappe: $14.100 | Limonada de coco 16 oz: $21.600 | Limonada de coco 12 oz: $16.200
Jugo natural 12 oz: $13.000 | Gaseosa 250 ml: $3.800 | Gaseosa 400 ml: $4.900
Agua 280 ml: $1.700 | Agua 600 ml: $3.300
Jarra sangría del día: $97.200 | Media jarra: $49.700 | Copa: $16.200
Botella vino tinto 750 ml: $97.200 | Botella vino blanco 750 ml: $97.200
Botella Old Parr 500 ml: $194.400 | Old Parr 750 ml: $248.400 | Old Parr 1000 ml: $302.400
Botella Buchanans Deluxe 750 ml: $259.200
Cerveza Costeña lata 330 ml: $5.400 | Budweiser lata 269 ml: $5.400 | Poker lata 330 ml: $6.500
Águila lata light 330 ml: $6.500 | Águila lata 330 ml: $6.500
Corona botella 210 ml: $6.000 | Club Colombia lata 330 ml: $7.100 | Stella lata 269 ml: $7.600
Adición michelada: $3.300
"""),

    art(
        title='Alimentos y Bebidas — carta terraza/piscina, eventos, desayunos y refrigerios Anas Mai/Maziruma 2026',
        category='alimentos-bebidas',
        content="""\
CARTA TERRAZA / PISCINA ANAS MAI

PLATOS
Alitas BBQ: $26.000 | Hamburguesitas x3 und.: $48.600 | Hamburguesitas de panceta: $32.400
Hamburguesa de queso: $36.800 | Montaditos de mariscos: $46.500 | Carimañolas de carne: $5.400
Fritura de mariscos: $34.600 | Calamares fritos: $34.600 | Mazorquitas: $23.800
Pollo laqueado: $38.900 | Costillas BBQ: $37.800 | La parrilla: $70.200
Pizza familiar x8 porciones: $67.000 | Pizza mediana x4: $34.600

─────────────────────────────────────────────────────────────

CARTA EVENTOS — ANAS MAI / MAZIRUMA

Paquete menú especial 1 proteína (150 g, 1 harina, 1 ensalada, 1 bebida, 1 postre; sin mariscos): $75.600
Paquete menú especial 2 proteínas (2x100 g, 1 harina, 1 ensalada, 1 bebida, 1 postre; sin mariscos): $91.800
Nota: desechables (J1) se cobran a partir de 10 unidades.

─────────────────────────────────────────────────────────────

DESAYUNOS — ANAS MAI / MAZIRUMA

Desayuno americano: $19.500 | Desayuno Anas Mai: $24.900 | Desayuno con chicharrón: $41.100
Porción de carne x150 g: $17.300 | Porción pechuga/cerdo x150 g: $10.800 | Porción de huevos: $5.400
Porción huevos con carnes frías: $7.600 | Porción queso x100 g: $7.600 | Patacones x2 und: $3.300
Papa francesa: $8.700 | Arepa x2 und: $4.400

MENÚ EMPRESARIAL EJECUTIVO: 1 caldo, 1 proteína 150 g, 2 harinas, 1 ensalada, 1 bebida: $36.000

MENÚ PASADÍA ANAS MAI / MAZIRUMA
  Asados Anas Mai (proteína 180 g + papas saladas, bollo, ensalada fresca y bebida): $36.000
  Maziruma (1 proteína 150 g, 2 harinas, 1 ensalada, 1 bebida): $36.000

─────────────────────────────────────────────────────────────

REFRIGERIOS — ANAS MAI / MAZIRUMA

Sándwich jamón y queso: $8.100 | Helado con frutas: $14.600 | Arepuela dulce: $3.300
Arepuela de huevo: $4.000 | Arepa de queso: $4.400 | Arepas rellenas mixtas: $8.700
Arepas de chichaguare: $4.900 | Papa rellena: $4.400 | Carimañola carne: $5.400
Empanada frita: $4.400 | Dedito de queso: $4.400 | Patacón relleno especial: $10.800
Arroz con leche: $8.100 | Peto: $6.500 | Parfait: $15.700
Ensalada de frutas: $13.500 | Fruta mano (manzana o pera): $5.400

REFRIGERIOS FUERTES
Crepes de pollo + pan francés: $24.900 | Canelón de pollo + pan francés: $24.900
Canelón florentino + pan francés: $21.600 | Rollo de pollo francés + pan francés: $30.300
Wrap de pollo: $21.600 | Pincho mixto (pollo, chorizo, butifarra) + papas: $19.500
Pincho (chorizo y butifarra) + papas: $13.000 | Sándwich pollo en pan casero + bebida: $23.800
Sándwich pollo en pan francés + bebida: $21.600 | Mini perro: $10.800 | Perro caliente: $13.000
Mini hamburguesa: $17.300 | Hamburguesa: $27.000

PASABOCAS / PICADAS (por unidad)
Albóndigas orientales: $3.800 | Bon bombones de pollo: $3.300 | Croquetas de pollo x60 g: $11.900
Mini maicito: $5.400 | Mini deditos de queso: $2.700 | Mini empanadas de pollo: $2.700
Mini pincho de pollo x60 g: $8.700 | Tostadas de camarón al gratín: $13.000
Palitos de pescado: $5.400 | Rollitos de jamón y queso: $6.500

─────────────────────────────────────────────────────────────

CAFETERÍA ANAS MAI / KIOSKO MAZIRUMA

Chiclets pequeño: $700 | Chiclets grande: $2.700 | Menta: $300 | Confite de café: $300
Bom Bom Bum: $900 | Manimoto: $3.300 | Manicero: $2.200 | Papas Margarita: $4.400
Detodito: $4.900 | Cheese Tris: $3.800 | Platanitos: $3.800 | Boliqueso: $3.500
Doritos: $4.400 | Popetas: $4.900 | Chocolatina: $1.700 | Galletas: $2.200

─────────────────────────────────────────────────────────────

LICORES Y BEBIDAS — ANAS MAI / MAZIRUMA

Whisky Sello Rojo 700 cc: $140.400 | Whisky Sello Rojo 1000 cc: $162.000
Whisky Black & White 700 cc: $118.800 | Whisky Black & White 1000 cc: $140.400
Whisky Old Parr 500 cc: $194.400 | Old Parr 750 cc: $248.400 | Old Parr 1000 cc: $302.400
Whisky Buchanans Deluxe 750 cc: $259.200 | Buchanans Master 750 cc: $291.600
Aguardiente Antioqueño 750 cc: $86.400 | Antioqueño Tetra Pack 1050 cc: $97.200
Ron Medellín 750 cc: $97.200 | Ron Medellín Tetra Pack 1050 cc: $118.800
Vino tinto 750 ml: $97.200 | Vino blanco 750 ml: $97.200
Cócteles de evento con licor: $21.600 | Cócteles de evento sin licor: $13.000
Limonada cerezada: $14.100 | Descorche de whisky: $41.100 | Descorche licores nacionales/vinos: $27.000
Descorche barra de cóctel 100-150 pax: $334.800 | Descorche barra cóctel >151 pax: $442.800
Power x500 ml: $4.400 | Gatorade x600 ml: $6.500 | Gaseosa 1,5 L: $9.800 | Gaseosa 3 L: $14.100
Gaseosa 400 ml: $4.900 | Gaseosa 250 ml: $3.800 | Soda: $5.400 | Jugo Tetra pack 200 ml: $3.800
Jugo natural 10 oz: $4.400 | Agua p300: $1.700 | Agua p600: $3.300
Mini pony malta 200 ml: $3.300 | Bon yurt con Zucaritas: $5.400 | Avena bolsa 200 ml: $4.400
Cervezas: Costeña lata 330 ml $5.400 | Budweiser 269 ml $5.400 | Poker 330 ml $6.500
Águila light 330 ml $6.500 | Águila 330 ml $6.500 | Corona 210 ml $6.000
Club Colombia 330 ml $7.100 | Stella 269 ml $7.600 | Adición michelada $3.300
"""),

    # =========================================================
    # POLICIES
    # =========================================================
    art(
        title='Políticas generales — afiliación, identificación y paz y salvo',
        purpose='policy',
        category='politicas',
        content="""\
POLÍTICAS GENERALES COMFAGUAJIRA 2026

IDENTIFICACIÓN OBLIGATORIA
Para acceder a las tarifas diferenciales de afiliado es indispensable presentar la
cédula de ciudadanía u otro documento de identificación válido.

PAZ Y SALVO EMPRESARIAL
Las empresas afiliadas deben estar a paz y salvo con sus aportes a Comfaguajira para
que sus empleados tengan acceso a las tarifas correspondientes por categoría.

NORMAS DE CONVIVENCIA (Anas Mai / Maziruma / Polideportivo)
  • Prohibido el ingreso de bebidas alcohólicas y sustancias psicoactivas externas.
  • Prohibido el ingreso de animales o mascotas.
  • A partir de 5 años de edad todo niño cancela el plan.
  • Para el ingreso a piscinas es obligatorio vestido de baño reglamentario (lycra de algodón o similar).
  • Comfaguajira se reserva el derecho de admisión.
  • El conductor del transporte no puede realizar paradas no autorizadas.

CANCELACIÓN DE RESERVAS (Anas Mai / Maziruma)
  • Más de 60 días antes del evento: 15% de retención sobre el total
  • 59 a 31 días: 25% de retención
  • 30 a 15 días: 50% de retención
  • 14 días o menos: no hay devolución del anticipo

PASADÍAS CON TRANSPORTE
  • Requieren reservación previa y pago anticipado en sedes de atención.
  • Presentarse en el punto de partida 30 minutos antes de la hora establecida.
  • Presentar documento de identificación y carné de vacunación.
  • El servicio es personal e intransferible. Sujeto a disponibilidad y cupo mínimo.

ALOJAMIENTO MAZIRUMA
  • Check-in: 3:00 p.m. | Check-out: hasta las 12:00 m.
  • Multa por salida tardía: $10.000 por persona.
  • Niños menores de 5 años no pagan alojamiento (pagan solo seguro hotelero por noche).
"""),

    # =========================================================
    # SALES SCRIPTS
    # =========================================================
    art(
        title='Cómo responder objeciones sobre tarifas y valor del servicio',
        purpose='sales_scripts',
        category='ventas',
        content="""\
Objeción: "Está muy caro"
Respuesta: Como afiliado Cat A pagas entre el 20% y el 30% de lo que paga el público general.
Un pasadía Anas Mai para Cat A es $38.400 todo incluido (almuerzo + piscinas), mientras el
público general paga $54.000. El alojamiento en Maziruma en habitación sencilla Cat A es $81.200
frente a $223.200 particular. El subsidio está incorporado en tu afiliación — es un beneficio que
ya tienes, solo hay que usarlo.
Cierre: ¿Qué servicio te interesa? Te confirmo exactamente cuánto pagas con tu categoría.

Objeción: "No sé qué categoría tengo"
Respuesta: La categoría la determina tu salario: A si ganas hasta 2 SMLV, B entre 2 y 4 SMLV,
C si superas 4 SMLV. Si no estás seguro, con tu cédula podemos verificarlo en cualquier sede.
Cierre: ¿Me das tu cédula y te confirmo la categoría ahora mismo?

Objeción: "El trámite del crédito es complicado"
Respuesta: Solo necesitas cédula, certificado laboral y las últimas colillas de pago. El estudio
cuesta $20.000 y el descuento va directamente por nómina. Para Cat A la tasa es 1.4% mensual,
una de las más bajas del mercado para libre inversión.
Cierre: ¿Para qué necesitas el crédito? Así te explico el monto aproximado que podrías solicitar.

Objeción: "No sé si lo voy a usar"
Respuesta: Si tu empresa ya está afiliada, el beneficio es tuyo sin costo adicional. Recreación,
salud, educación, crédito — puedes empezar por lo que más te interese hoy.
Cierre: ¿Qué es lo que más llama tu atención del portafolio?

Objeción: "Quiero reservar pero me da pereza ir a una sede"
Respuesta: Para algunos servicios como el gimnasio, las escuelas deportivas o los cursos puedes
consultar horarios y disponibilidad aquí mismo. Para pasadías y alojamiento la reserva y el pago
se hacen directamente en las sedes o UISES de atención.
Cierre: ¿Prefieres Anas Mai en Riohacha o Maziruma en Dibulla para el pasadía?
"""),
]

# ── Create articles ───────────────────────────────────────────────────────────
created = 0
for a in ARTICLES:
    KBArticle.objects.create(
        organization=org,
        title=a['title'],
        purpose=a.get('purpose', 'faq'),
        content=a['content'],
        category=a.get('category', 'tarifario-2026'),
        tags=a.get('tags', []),
        status='published',
        is_active=True,
    )
    created += 1
    print(f"[{a.get('purpose','faq').upper()[:6]}] [{a.get('category','—')}] {a['title']}")

print(f"\nTotal: {created} articulos creados / actualizados para {org.name}")

from collections import Counter
counts = Counter(KBArticle.objects.filter(organization=org).values_list('purpose', flat=True))
print("\nPor purpose:")
for p, c in sorted(counts.items()):
    print(f"  {p}: {c}")
cats = Counter(KBArticle.objects.filter(organization=org).values_list('category', flat=True))
print("\nPor categoría:")
for c, n in sorted(cats.items()):
    print(f"  {c}: {n}")
