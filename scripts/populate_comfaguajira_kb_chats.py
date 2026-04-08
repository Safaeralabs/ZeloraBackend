import django
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.knowledge_base.models import KBArticle
from apps.accounts.models import Organization

org = Organization.objects.get(id='d620ebfb-71b3-48f6-ab9e-1f187f93d9fb')
print('Org:', org.name)
print('Artículos existentes:', KBArticle.objects.filter(organization=org).count())

articles = [

    # ===== FAQ — extraídos de chats reales =====

    {
        'title': 'Subsidio familiar — preguntas frecuentes',
        'purpose': 'faq',
        'content': (
            "P: ¿Qué es el subsidio familiar?\n"
            "R: Es un beneficio económico que Comfaguajira entrega a los trabajadores afiliados por cada hijo menor de edad a cargo. "
            "Puede ser en dinero (subsidio monetario), en especie (kits escolares, mercados) o en servicios (recreación, salud, educación).\n\n"
            "P: ¿Cuándo se realizan los pagos del subsidio monetario?\n"
            "R: El pago se realiza el último día hábil de cada mes (28 o 29 en febrero, 30 o 31 en los demás meses).\n\n"
            "P: ¿A qué hijos les corresponde el subsidio?\n"
            "R: A hijos legítimos o adoptivos menores de edad, o mayores de edad si son inválidos o estudiantes activos. "
            "También aplica para hijos de compañera/o permanente debidamente registrados.\n\n"
            "P: ¿Cuándo entregan los kits escolares?\n"
            "R: La entrega de kits varía por municipio y según el calendario escolar. "
            "Consultar en la sede de Comfaguajira más cercana o en www.comfaguajira.co la convocatoria vigente.\n\n"
            "P: ¿Qué hago si no me llegó el pago del subsidio?\n"
            "R: Comunicarse con Comfaguajira con su nombre completo, número de documento y teléfono para verificar el estado. "
            "Es posible que falte actualizar datos bancarios o que haya una novedad en la afiliación.\n\n"
            "P: ¿Cómo reclamar el kit escolar?\n"
            "R: Acercase a la sede de Comfaguajira del municipio correspondiente con el documento del afiliado y los certificados de estudio de los hijos."
        ),
    },

    {
        'title': 'Cambio de medio de pago del subsidio',
        'purpose': 'faq',
        'content': (
            "P: ¿Cómo cambio el número de cuenta o Daviplata donde me consignan el subsidio?\n"
            "R: Debe acercarse a las oficinas de Comfaguajira con su cédula y los datos del nuevo medio de pago (número de cuenta, Nequi, Daviplata u otro) "
            "para registrar la novedad. También puede consultar si el trámite está disponible en la página web www.comfaguajira.co.\n\n"
            "P: ¿Cuánto demora en verse reflejado el cambio de medio de pago?\n"
            "R: El cambio normalmente se aplica en el siguiente ciclo de pago (fin de mes). Si ya pasó el corte y realizó el cambio después, "
            "el primer pago en el nuevo medio será el mes siguiente.\n\n"
            "P: ¿Qué medios de pago acepta Comfaguajira?\n"
            "R: Daviplata, cuentas bancarias (Bancolombia, Davivienda, entre otros) y otros medios electrónicos autorizados. "
            "Consultar los medios vigentes directamente con la sede.\n\n"
            "P: ¿Qué hago si actualicé el medio de pago pero el pago no llegó?\n"
            "R: Verificar con Comfaguajira que el cambio quedó registrado correctamente y que no hay novedades en la afiliación. "
            "Suministrar nombre completo, cédula y teléfono para que puedan revisar el caso."
        ),
    },

    {
        'title': 'Subsidio al desempleo — preguntas frecuentes',
        'purpose': 'faq',
        'content': (
            "P: ¿Qué es el subsidio al desempleo de Comfaguajira?\n"
            "R: Es un beneficio temporal para trabajadores desvinculados que estuvieron afiliados a Comfaguajira. "
            "Incluye apoyo económico y capacitaciones para reincorporación laboral.\n\n"
            "P: ¿Cómo me postulo al subsidio al desempleo?\n"
            "R: Ingresar a www.comfaguajira.co, sección Subsidio, y seguir el proceso de registro. "
            "También puede acercarse a la sede más cercana con cédula y documentos que acrediten la desvinculación laboral.\n\n"
            "P: ¿Las capacitaciones son obligatorias?\n"
            "R: Sí, las capacitaciones son requisito para mantener el subsidio. Son presenciales en las sedes de Comfaguajira.\n\n"
            "P: ¿Puedo hacer las capacitaciones en una sede diferente a la de mi municipio?\n"
            "R: Depende de la disponibilidad. Si vive en un municipio con sede propia de Comfaguajira, consultar si puede trasladar "
            "las capacitaciones a esa sede. Comunicarse previamente con la oficina que lo citó.\n\n"
            "P: ¿Cómo registro mi cuenta Daviplata para recibir el pago del subsidio al desempleo?\n"
            "R: El registro del medio de pago se hace directamente en las oficinas de Comfaguajira al momento de la afiliación al programa."
        ),
    },

    {
        'title': 'Subsidio de vivienda — preguntas frecuentes',
        'purpose': 'faq',
        'content': (
            "P: ¿Comfaguajira otorga subsidio de vivienda?\n"
            "R: Sí. Comfaguajira ofrece subsidio de vivienda para construcción en lote propio y otras modalidades para afiliados activos.\n\n"
            "P: ¿Cuáles son los requisitos para el subsidio de vivienda?\n"
            "R: Los requisitos básicos incluyen: ser afiliado activo, no ser propietario de otra vivienda, "
            "y cumplir con criterios de ingresos según la modalidad. Para el listado completo y actualizado "
            "acercase a la Oficina de Vivienda de Comfaguajira.\n\n"
            "P: ¿Dónde queda la Oficina de Vivienda?\n"
            "R: Oficina de Vivienda — UIS Riohacha, Calle 14A No. 10-110. Horario: lunes a viernes, 8:00 a 11:00 a.m. y 2:00 a 4:00 p.m. "
            "Tel: 605 727 0204 ext. 5006 y 5009. WhatsApp: 310 568 5189.\n\n"
            "P: ¿Qué documentos necesito para tramitar el subsidio de vivienda?\n"
            "R: Consultar directamente en la Oficina de Vivienda ya que los documentos varían según la modalidad (lote propio, mejoramiento, compra). "
            "En general se requiere: cédula, escrituras del lote (si aplica), certificados laborales y formulario de solicitud."
        ),
    },

    {
        'title': 'Afiliaciones — cómo inscribirse y quiénes pueden ser beneficiarios',
        'purpose': 'faq',
        'content': (
            "P: ¿Cómo sé si estoy afiliado a Comfaguajira?\n"
            "R: Ingresar a www.comfaguajira.co, sección Subsidio → Afiliaciones, y seguir las instrucciones para consultar el estado. "
            "También puede comunicarse directamente con su número de cédula.\n\n"
            "P: ¿Cómo activo mi afiliación?\n"
            "R: La afiliación la realiza el empleador. Si ya aparece en el sistema pero no está activo, "
            "comunicarse con Comfaguajira con nombre completo, documento y datos del empleador para verificar la novedad.\n\n"
            "P: ¿A quiénes puedo afiliar como beneficiarios?\n"
            "R: Como beneficiarios se pueden afiliar: hijos legítimos o adoptivos menores de edad (o mayores si son inválidos o estudiantes), "
            "cónyuge o compañera/o permanente, y padres que dependan económicamente del afiliado (verificar condiciones). "
            "No pueden afiliarse hermanos ni otros familiares.\n\n"
            "P: ¿Cómo agrego a mi cónyuge o a mis hijos como beneficiarios?\n"
            "R: Acercarse a las oficinas de Comfaguajira con el registro civil o tarjeta de identidad de los hijos, "
            "y con el registro civil de matrimonio o declaración de unión libre para el/la cónyuge.\n\n"
            "P: ¿Cómo obtengo un certificado de afiliación?\n"
            "R: Solicitarlo en las oficinas de Comfaguajira presentando la cédula, o consultar si está disponible en la plataforma web. "
            "También puede pedirlo a través del chat con nombre completo y número de documento."
        ),
    },

    {
        'title': 'Documentos y certificados — cómo enviarlos',
        'purpose': 'faq',
        'content': (
            "P: ¿A qué correo envío los certificados de estudio de mis hijos?\n"
            "R: Los certificados de estudio se envían directamente a Comfaguajira. Consultar el correo de radicación vigente "
            "en www.comfaguajira.co o en la sede más cercana, ya que puede variar según el municipio.\n\n"
            "P: ¿Qué documentos debo actualizar para mantener el subsidio?\n"
            "R: Certificados de estudio vigentes de hijos mayores de 18 años que aún estudian (debe renovarse cada año). "
            "Si el hijo tiene discapacidad, se requiere certificado médico actualizado.\n\n"
            "P: ¿Cuándo debo entregar los certificados de estudio?\n"
            "R: Generalmente al inicio del año escolar o cuando Comfaguajira lo solicite. "
            "Consultar el calendario de actualización de documentos en la página web o la sede.\n\n"
            "P: ¿Cómo solicito un certificado de afiliación?\n"
            "R: Comunicarse con Comfaguajira vía chat, teléfono o presencialmente con su nombre completo y número de documento. "
            "El certificado se genera en las oficinas o puede ser enviado al correo registrado."
        ),
    },

    {
        'title': 'Foniñez — programa para niños afiliados',
        'purpose': 'faq',
        'content': (
            "P: ¿Qué es Foniñez?\n"
            "R: Foniñez es el programa de Comfaguajira orientado al bienestar y desarrollo de los hijos de los afiliados. "
            "Incluye actividades recreativas, subsidios y beneficios específicos para niños y jóvenes.\n\n"
            "P: ¿Cómo inscribo a mis hijos en el programa Foniñez?\n"
            "R: Acercarse a la sede de Comfaguajira con el registro civil o tarjeta de identidad de los menores "
            "y la documentación del afiliado titular para realizar la inscripción.\n\n"
            "P: ¿Cómo sé si mis hijos ya están en el programa?\n"
            "R: Comunicarse con Comfaguajira con el nombre del afiliado, número de documento y los datos del menor "
            "para verificar si ya están registrados en el sistema.\n\n"
            "P: ¿Cuál es la diferencia entre Foniñez y Crecer Sano?\n"
            "R: Foniñez es el programa general de beneficios para los hijos afiliados (recreación, subsidios, actividades). "
            "Crecer Sano es el programa de nutrición y salud específicamente para niños de 6 meses a 14 años "
            "que incluye consulta nutricional y subsidio en fórmulas alimenticias."
        ),
    },

    {
        'title': 'Formación laboral técnica — SENA y cursos',
        'purpose': 'faq',
        'content': (
            "P: ¿Comfaguajira tiene programas técnicos o cursos de formación laboral?\n"
            "R: Sí. El Centro de Formación para el Trabajo y Desarrollo Humano de Comfaguajira ofrece "
            "programas técnicos laborales por competencias (ej: Auxiliar Administrativo), cursos cortos e informales, "
            "inglés y preparación para licencia de conducción.\n\n"
            "P: ¿Cómo me inscribo en un programa técnico?\n"
            "R: Consultar los programas disponibles en www.comfaguajira.co o acercarse al Centro de Formación. "
            "Los requisitos varían por programa — en general se pide cédula, diploma de bachiller (para técnicos) y formulario de inscripción.\n\n"
            "P: ¿Tengo descuento por ser afiliado?\n"
            "R: Sí. Los afiliados tienen tarifas preferenciales en los programas de formación. "
            "Categoría A puede acceder a algunos cursos gratuitos o con subsidio alto.\n\n"
            "P: ¿Cómo solicito certificados de cursos ya realizados?\n"
            "R: Comunicarse con el Centro de Formación con nombre completo, número de documento y detalles del curso. "
            "Puede solicitarse por chat, teléfono o presencialmente."
        ),
    },

    {
        'title': 'Datos de contacto y horarios de atención',
        'purpose': 'faq',
        'content': (
            "P: ¿Cuál es el teléfono de Comfaguajira?\n"
            "R: Sede principal Riohacha: 605 727 0204. WhatsApp de atención: 310 568 5189.\n\n"
            "P: ¿Cuál es el horario de atención presencial?\n"
            "R: Lunes a viernes de 8:00 a.m. a 11:00 a.m. y de 2:00 a 4:00 p.m. en la UIS Riohacha (Calle 14A No. 10-110). "
            "Horarios pueden variar por sede y servicio — consultar en www.comfaguajira.co.\n\n"
            "P: ¿Tiene sedes en otros municipios?\n"
            "R: Sí. Comfaguajira tiene presencia en varios municipios de La Guajira. "
            "Consultar las sedes disponibles en www.comfaguajira.co o llamar a la sede principal.\n\n"
            "P: ¿Cómo puedo hacer un trámite sin ir a la oficina?\n"
            "R: Muchos trámites de subsidio están disponibles en la plataforma web www.comfaguajira.co. "
            "También puede comunicarse por chat en el sitio web o llamar al WhatsApp de atención (310 568 5189)."
        ),
    },

    # ===== BUSINESS — Tono de marca y presentación del agente =====

    {
        'title': 'Tono de marca y protocolo de atención',
        'purpose': 'business',
        'content': (
            "Qué ofrecemos:\n"
            "Comfaguajira atiende con calidez, formalidad y orientación al servicio. "
            "El tono es respetuoso y profesional, usando tratamiento de 'señor' o 'señora' al dirigirse a los usuarios.\n\n"
            "Para quién:\n"
            "Este protocolo aplica para todas las interacciones con afiliados, beneficiarios y público general.\n\n"
            "Por qué elegirnos:\n"
            "El equipo de atención de Comfaguajira — históricamente representado por Enrique Mejía Toro y Alicia López — "
            "se caracteriza por personalizar la respuesta y verificar caso a caso, nunca dar información genérica sin validar.\n\n"
            "Diferenciadores:\n"
            "Saludo formal con nombre del asesor: 'Buenos días/Buenas tardes, le habla su servidor [Nombre]'. "
            "Solicita datos para verificar antes de responder: nombre completo, número de documento y teléfono. "
            "Redirige a herramientas digitales cuando es posible: www.comfaguajira.co. "
            "Cierra con confirmación de seguimiento: 'Estaremos validando para darle respuesta lo antes posible'."
        ),
    },

    # ===== SALES SCRIPTS — Objeciones reales de los chats =====

    {
        'title': 'Objeciones sobre pagos y demoras',
        'purpose': 'sales_scripts',
        'content': (
            "Objeción: No me ha llegado el pago del subsidio\n"
            "Respuesta: Entiendo la preocupación. Los pagos se realizan el último día hábil de cada mes. "
            "Si ya pasó esa fecha y no recibió el depósito, puede ser por una novedad en la afiliación o "
            "datos bancarios desactualizados. Para revisarlo necesito su nombre completo, número de documento y teléfono.\n"
            "Cierre: ¿Me comparte esos datos para validar el estado de su pago?\n\n"
            "Objeción: Cambié de Daviplata y ahora no me llega el subsidio\n"
            "Respuesta: Es un caso frecuente. Cuando se cambia el medio de pago, el nuevo dato debe quedar registrado "
            "en el sistema antes del cierre del mes. Si el cambio se hizo tarde, el primer pago en el nuevo medio "
            "llega el mes siguiente. Podemos verificar que el cambio quedó bien registrado.\n"
            "Cierre: ¿Cuándo realizó el cambio y tiene el número del nuevo medio de pago a la mano?\n\n"
            "Objeción: Hace meses no recibo el beneficio\n"
            "Respuesta: Eso definitivamente hay que revisarlo. Puede deberse a una desvinculación laboral del empleador, "
            "documentos vencidos (certificados de estudio) o un dato bancario incorrecto. "
            "Con sus datos podemos ver exactamente qué pasó.\n"
            "Cierre: ¿Me da su nombre, cédula y teléfono para hacer la consulta?"
        ),
    },

    {
        'title': 'Objeciones sobre trámites y documentos',
        'purpose': 'sales_scripts',
        'content': (
            "Objeción: No sé a dónde enviar los certificados\n"
            "Respuesta: Es muy común no saber por dónde empezar. Le recomiendo ingresar a www.comfaguajira.co, "
            "sección Subsidio → Afiliaciones, donde encontrará el paso a paso y los formatos necesarios. "
            "Si prefiere, también puede acercarse a la sede más cercana con los documentos.\n"
            "Cierre: ¿Está en Riohacha o en otro municipio? Así le indico la sede más próxima.\n\n"
            "Objeción: El trámite de afiliación es complicado\n"
            "Respuesta: En realidad es bastante sencillo una vez se sabe qué llevar. "
            "Para afiliación de beneficiarios solo necesita cédula, registros civiles de los hijos y "
            "documento de matrimonio o unión libre para el/la cónyuge. Todo se hace en la sede en una sola visita.\n"
            "Cierre: ¿Cuál es el beneficiario que quiere registrar — hijo, cónyuge u otro?\n\n"
            "Objeción: Ya mandé los documentos pero no hay respuesta\n"
            "Respuesta: Estaremos validando para darle respuesta lo antes posible. "
            "Si ya pasaron más de 5 días hábiles desde el envío, le sugiero comunicarse directamente "
            "al 605 727 0204 o por WhatsApp al 310 568 5189 para hacer seguimiento.\n"
            "Cierre: ¿Recuerda la fecha en que envió los documentos y al correo que los mandó?"
        ),
    },

    # ===== POLICY — Privacidad y datos personales =====

    {
        'title': 'Política de tratamiento de datos personales',
        'purpose': 'policy',
        'content': (
            "Nombre: Autorización de tratamiento de datos personales\n"
            "Condiciones:\n"
            "Al comunicarse con Comfaguajira y suministrar datos personales, el usuario autoriza a Comfaguajira "
            "a utilizarlos de manera confidencial, segura, leal y transparente, en los términos de la Ley 1581 de 2012 "
            "y el Decreto 1377 de 2013, para el desarrollo de campañas promocionales, oferta de servicios y "
            "programas de fidelización diseñados, implementados y administrados por Comfaguajira o terceros autorizados.\n\n"
            "Los datos solicitados para gestionar consultas son: nombre completo, número de documento, "
            "correo electrónico y teléfono.\n\n"
            "Excepciones:\n"
            "El usuario puede revocar su autorización en cualquier momento comunicándose con Comfaguajira. "
            "Los datos no serán compartidos con terceros sin autorización expresa, salvo obligación legal."
        ),
    },

    {
        'title': 'Horarios y sedes de atención',
        'purpose': 'policy',
        'content': (
            "Nombre: Horarios y ubicación de sedes\n"
            "Condiciones:\n"
            "Sede principal — UIS Riohacha, Calle 14A No. 10-110.\n"
            "Horario: lunes a viernes, 8:00 a.m. a 11:00 a.m. y 2:00 p.m. a 4:00 p.m.\n"
            "Teléfono: 605 727 0204 (extensiones 5006 y 5009 para Vivienda).\n"
            "WhatsApp: 310 568 5189 (llamadas y mensajes).\n"
            "Plataforma web: www.comfaguajira.co\n\n"
            "Centros recreativos:\n"
            "Anas Mai — Riohacha. Maziruma — Dibulla. Check-in: 3:00 p.m. | Check-out: 12:00 m.\n\n"
            "Excepciones:\n"
            "Los horarios pueden variar en días festivos o por disposiciones administrativas. "
            "Verificar disponibilidad antes de acudir presencialmente."
        ),
    },
]

created = 0
for art in articles:
    KBArticle.objects.create(
        organization=org,
        title=art['title'],
        purpose=art['purpose'],
        content=art['content'],
        category='manual',
        tags=[],
        is_active=True,
    )
    created += 1
    print(f"[{art['purpose'].upper()[:6]}] {art['title']}")

print(f"\nTotal nuevos: {created} artículos creados")

# Summary
from collections import Counter
counts = Counter(KBArticle.objects.filter(organization=org).values_list('purpose', flat=True))
print("\nTotal por categoría:")
for purpose, count in sorted(counts.items()):
    print(f"  {purpose}: {count}")
print(f"  TOTAL: {sum(counts.values())}")
