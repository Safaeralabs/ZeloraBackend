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

articles = [
    # ===== BUSINESS (Pitch) =====
    {
        'title': 'Qué es Comfaguajira',
        'purpose': 'business',
        'content': (
            "Qué ofrecemos:\n"
            "Comfaguajira es la Caja de Compensación Familiar del departamento de La Guajira, Colombia. "
            "Brinda servicios integrales de bienestar a trabajadores afiliados y sus familias: recreación, salud, "
            "educación, crédito social, vivienda, cultura, deportes, turismo y programas especiales como Adulto Mayor y Crecer Sano.\n\n"
            "Para quién:\n"
            "Trabajadores dependientes afiliados (y sus familias) en empresas inscritas en Comfaguajira. "
            "Los afiliados se clasifican en Categoría A (salario ≤ 2 SMLV), Categoría B (2-4 SMLV) y Categoría C (> 4 SMLV). "
            "Algunos servicios también están disponibles para el público en general (no afiliados) a tarifas diferenciadas.\n\n"
            "Por qué elegirnos:\n"
            "Al ser una Caja de Compensación, las tarifas para afiliados son considerablemente más bajas que el sector privado: "
            "entre 30% y 80% de descuento dependiendo de la categoría. Los afiliados de Categoría A reciben el mayor subsidio.\n\n"
            "Diferenciadores:\n"
            "Cobertura integral: un solo afiliado accede a más de 10 líneas de servicios. "
            "Presencia regional: centros recreativos Anas Mai (Riohacha) y Maziruma (Dibulla), teatro Akuaipaa, "
            "sedes educativas y clínica IPS en La Guajira. "
            "Programas de bienestar con enfoque social: subsidio del 75% en alimentación para niños en Crecer Sano, "
            "créditos a tasas preferenciales, Escuela de Artes accesible."
        ),
    },
    {
        'title': 'Portafolio completo de servicios',
        'purpose': 'business',
        'content': (
            "Qué ofrecemos:\n"
            "1. Recreación: Pasadías, alojamiento y uso de instalaciones en Anas Mai (Riohacha) y Maziruma (Dibulla).\n"
            "2. Turismo: Paquetes a Cabo de la Vela, Rancherías culturales y Alta Guajira.\n"
            "3. Educación: Cursos informales, formación laboral técnica, inglés, licencia de conducción, escuela formal en Hatonuevo.\n"
            "4. Crédito Social: Préstamos a tasas del 1.4-1.6% mensual con hasta 60 cuotas.\n"
            "5. Salud IPS: Consultas médicas generales y especializadas, laboratorio, terapias.\n"
            "6. Vivienda: Subsidio de vivienda y certificaciones para trámites.\n"
            "7. Cultura: Escuela de Artes: pintura, música, teatro, danza.\n"
            "8. Deportes: Escuelas deportivas, torneos, gimnasio.\n"
            "9. Adulto Mayor: Programa mensual de actividades y bienestar.\n"
            "10. Crecer Sano: Nutrición y seguimiento para niños de 6 meses a 14 años.\n"
            "11. Alquiler de espacios: Aulas, auditorio, Teatro Akuaipaa para eventos.\n\n"
            "Para quién:\n"
            "Afiliados y sus familias. Público general puede acceder a algunos servicios a tarifa no afiliado.\n\n"
            "Por qué elegirnos:\n"
            "Un solo vínculo de afiliación abre las puertas a todas estas líneas. "
            "Los empleadores que se inscriben en Comfaguajira ofrecen a sus trabajadores un beneficio social completo.\n\n"
            "Diferenciadores:\n"
            "Única caja de compensación del departamento de La Guajira. "
            "Infraestructura propia: 2 centros recreativos, teatro, IPS y sedes educativas."
        ),
    },
    {
        'title': 'Sistema de categorías y subsidios',
        'purpose': 'business',
        'content': (
            "Qué ofrecemos:\n"
            "Comfaguajira aplica un sistema de categorías salariales que determina el valor a pagar por cada servicio:\n"
            "Categoría A: salario menor o igual a 2 SMLV — mayor subsidio, tarifas más bajas.\n"
            "Categoría B: salario entre 2 y 4 SMLV — subsidio medio.\n"
            "Categoría C: salario mayor a 4 SMLV — menor subsidio, tarifas más cercanas al público general.\n\n"
            "Para quién:\n"
            "Todos los afiliados activos. La categoría se determina automáticamente por el salario reportado por el empleador.\n\n"
            "Por qué elegirnos:\n"
            "El subsidio garantiza que los trabajadores de menores ingresos paguen menos por los mismos servicios.\n\n"
            "Diferenciadores:\n"
            "Un pasadía que cuesta $65.000 al público general puede costar $10.800 para un afiliado Categoría A. "
            "El crédito social tiene tasa del 1.4% para Cat A frente al 1.6% para Cat C."
        ),
    },

    # ===== FAQ =====
    {
        'title': 'Crédito Social — preguntas frecuentes',
        'purpose': 'faq',
        'content': (
            "P: ¿Qué es el Crédito Social de Comfaguajira?\n"
            "R: Es un préstamo personal de bajo costo para afiliados activos. Permite financiar necesidades del hogar, educación, salud, viajes u otras.\n\n"
            "P: ¿Cuál es la tasa de interés?\n"
            "R: Depende de la categoría: Cat A = 1.4% mensual, Cat B = 1.5% mensual, Cat C = 1.6% mensual.\n\n"
            "P: ¿Cuánto puedo pedir y en cuántas cuotas?\n"
            "R: El monto máximo y el plazo dependen del salario y la capacidad de pago. Se puede pagar hasta en 60 cuotas.\n\n"
            "P: ¿Hay costo de estudio del crédito?\n"
            "R: Sí, el estudio de crédito tiene un costo de $20.000.\n\n"
            "P: ¿Quién puede solicitar el crédito?\n"
            "R: Cualquier trabajador afiliado activo. Consultar tiempo mínimo de afiliación requerido en sede.\n\n"
            "P: ¿Cómo se solicita?\n"
            "R: Acercándose a las oficinas de Comfaguajira con cédula, certificado laboral y colillas de pago recientes."
        ),
    },
    {
        'title': 'Recreación Anas Mai y Maziruma — preguntas frecuentes',
        'purpose': 'faq',
        'content': (
            "P: ¿Dónde están los centros recreativos?\n"
            "R: Anas Mai está en Riohacha y Maziruma está en Dibulla, La Guajira.\n\n"
            "P: ¿Qué incluye un pasadía?\n"
            "R: Acceso a piscinas, zonas verdes, canchas deportivas y áreas recreativas durante el día. No incluye alimentación.\n\n"
            "P: ¿Se puede pasar la noche?\n"
            "R: Sí, Maziruma ofrece alojamiento. El check-in es a las 3:00 p.m. y el check-out a las 12:00 m.\n\n"
            "P: ¿Cuánto cuesta el pasadía para afiliados?\n"
            "R: Cat A: $10.800 | Cat B: $16.200 | Cat C: $27.000 | No afiliado adulto: $65.000.\n\n"
            "P: ¿Se puede llevar mascota?\n"
            "R: No. Está prohibido el ingreso de mascotas a los centros recreativos.\n\n"
            "P: ¿Se requiere vestido de baño para la piscina?\n"
            "R: Sí, es obligatorio el uso de vestido de baño reglamentario para el acceso a las piscinas."
        ),
    },
    {
        'title': 'Turismo — preguntas frecuentes',
        'purpose': 'faq',
        'content': (
            "P: ¿Qué paquetes turísticos ofrece Comfaguajira?\n"
            "R: Ofrece paquetes a Cabo de la Vela, tours por Rancherías culturales y expediciones a la Alta Guajira.\n\n"
            "P: ¿Incluye transporte?\n"
            "R: Sí, los paquetes turísticos incluyen transporte desde el punto de salida acordado. Consultar detalles de cada paquete.\n\n"
            "P: ¿Se necesita ser afiliado para los paquetes turísticos?\n"
            "R: Los afiliados tienen tarifas preferenciales. El público general también puede participar a tarifa regular.\n\n"
            "P: ¿Cómo reservo?\n"
            "R: Comunicándose con las oficinas de Comfaguajira o a través de los canales oficiales para consultar disponibilidad y fechas."
        ),
    },
    {
        'title': 'Educación — preguntas frecuentes',
        'purpose': 'faq',
        'content': (
            "P: ¿Qué programas educativos ofrece Comfaguajira?\n"
            "R: Cursos informales (idiomas, manualidades, oficios), formación laboral técnica, educación formal en Hatonuevo y programas de inglés y licencia de conducción.\n\n"
            "P: ¿Cuánto cuestan los cursos informales?\n"
            "R: Entre $0 y $355.000 dependiendo del curso y la categoría del afiliado. Algunos son totalmente subsidiados para Cat A.\n\n"
            "P: ¿La Escuela de Artes tiene costo?\n"
            "R: Los programas de pintura, música, teatro y danza tienen tarifas accesibles o subsidiadas para afiliados.\n\n"
            "P: ¿Mi hijo puede ingresar a la escuela formal?\n"
            "R: Sí, Comfaguajira administra una institución de educación formal en Hatonuevo. Consultar cupos y requisitos de matrícula."
        ),
    },
    {
        'title': 'Salud IPS — preguntas frecuentes',
        'purpose': 'faq',
        'content': (
            "P: ¿Qué servicios de salud ofrece la IPS de Comfaguajira?\n"
            "R: Consultas médicas generales y con especialistas, laboratorio clínico, terapias físicas y otros servicios ambulatorios.\n\n"
            "P: ¿Cuánto cuesta la consulta médica general?\n"
            "R: Consulta médica general: $27.600. Consultas con especialistas entre $50.000 y $144.800 aproximadamente.\n\n"
            "P: ¿Atienden a no afiliados?\n"
            "R: Sí, la IPS puede atender público general a las tarifas correspondientes.\n\n"
            "P: ¿El programa Crecer Sano qué incluye?\n"
            "R: Seguimiento nutricional para niños de 6 meses a 14 años, consulta de nutrición a $13.000 (Cat A/B) y subsidio del 75% en fórmulas alimenticias.\n\n"
            "P: ¿Qué es el programa Adulto Mayor?\n"
            "R: Programa mensual de actividades de bienestar y salud para adultos mayores afiliados. Valor mensual: $5.900 (Cat A) o $11.800 (Cat B)."
        ),
    },
    {
        'title': 'Alquiler de espacios — preguntas frecuentes',
        'purpose': 'faq',
        'content': (
            "P: ¿Qué espacios se pueden arrendar en Comfaguajira?\n"
            "R: Aulas, auditorio y Teatro Akuaipaa (disponibles en Centro Desarrollo Educativo y Centro Anas Mai). Para eventos empresariales, sociales y culturales.\n\n"
            "P: ¿Se requiere ser afiliado para alquilar?\n"
            "R: No. Los espacios están disponibles para empresas y público general, aunque los afiliados pueden tener condiciones preferenciales.\n\n"
            "P: ¿Qué incluye el alquiler del auditorio?\n"
            "R: Normalmente sillas, escenario y sistemas básicos de sonido/iluminación. Los detalles específicos se coordinan al momento de la reserva.\n\n"
            "P: ¿Cómo reservo un espacio?\n"
            "R: Contactando directamente las oficinas de Comfaguajira para confirmar disponibilidad, tarifas y condiciones."
        ),
    },

    # ===== POLICY =====
    {
        'title': 'Política de cancelación de eventos y reservas',
        'purpose': 'policy',
        'content': (
            "Nombre: Cancelación de reservas — retención por tiempo\n"
            "Condiciones:\n"
            "Cancelación con más de 30 días de anticipación: retención del 15% del valor total.\n"
            "Cancelación entre 15 y 30 días: retención del 25%.\n"
            "Cancelación entre 8 y 14 días: retención del 50%.\n"
            "Cancelación con 7 días o menos: retención del 100% (sin reembolso).\n\n"
            "Excepciones:\n"
            "Cancelaciones por fuerza mayor debidamente documentadas pueden ser evaluadas caso a caso por la administración. "
            "Las reprogramaciones están sujetas a disponibilidad y deben solicitarse con anticipación."
        ),
    },
    {
        'title': 'Normas de convivencia — centros recreativos',
        'purpose': 'policy',
        'content': (
            "Nombre: Normas de conducta en Anas Mai y Maziruma\n"
            "Condiciones:\n"
            "Horario de check-in: 3:00 p.m. | Check-out: 12:00 m.\n"
            "Uso obligatorio de vestido de baño reglamentario en piscinas.\n"
            "Prohibido el ingreso de bebidas alcohólicas y sustancias psicoactivas.\n"
            "Prohibido el ingreso de mascotas.\n"
            "Respetar las zonas señalizadas y la capacidad máxima de cada área.\n"
            "Los menores de edad deben estar acompañados por un adulto responsable.\n"
            "El incumplimiento puede ocasionar la salida inmediata del centro sin reembolso.\n\n"
            "Excepciones:\n"
            "Las normas aplican por igual a afiliados y público general. "
            "Eventos especiales contratados pueden tener condiciones adicionales coordinadas con la administración."
        ),
    },
    {
        'title': 'Política de crédito social — condiciones',
        'purpose': 'policy',
        'content': (
            "Nombre: Crédito Social — términos y condiciones generales\n"
            "Condiciones:\n"
            "Tasas de interés: Categoría A = 1.4% m.v., Categoría B = 1.5% m.v., Categoría C = 1.6% m.v.\n"
            "Plazo máximo: 60 cuotas.\n"
            "Costo del estudio de crédito: $20.000 (no reembolsable).\n"
            "Monto aprobado sujeto a capacidad de pago y evaluación crediticia.\n"
            "Descuento de cuotas por nómina a través del empleador.\n"
            "Si el trabajador se desafilia, el saldo pendiente se hace exigible de inmediato.\n\n"
            "Excepciones:\n"
            "Trabajadores con embargos judiciales activos sobre el salario pueden tener restricciones. "
            "Consultar con la sede los requisitos vigentes de tiempo mínimo de afiliación."
        ),
    },
    {
        'title': 'Política de tarifas diferenciadas por categoría',
        'purpose': 'policy',
        'content': (
            "Nombre: Tarifas por categoría de afiliado\n"
            "Condiciones:\n"
            "Categoría A (≤ 2 SMLV): tarifa más subsidiada.\n"
            "Categoría B (2-4 SMLV): tarifa media.\n"
            "Categoría C (> 4 SMLV): menor subsidio.\n"
            "No afiliado: tarifa comercial plena.\n"
            "La categoría es determinada por el salario reportado por el empleador al momento de la liquidación de aportes.\n"
            "Los hijos y cónyuge del afiliado acceden a los servicios en la misma categoría del afiliado titular.\n\n"
            "Excepciones:\n"
            "Algunos servicios (laboratorio IPS, alquiler de espacios) pueden tener tarifa única independiente de la categoría. "
            "Verificar con la sede el detalle por servicio."
        ),
    },

    # ===== SALES SCRIPTS =====
    {
        'title': 'Objeciones más comunes — cómo responderlas',
        'purpose': 'sales_scripts',
        'content': (
            "Objeción: Está muy caro\n"
            "Respuesta: Un pasadía en el sector privado fácilmente cuesta $200.000 o más por persona. Con Comfaguajira, "
            "como afiliado Categoría A pagas $10.800 — más del 80% de descuento. Lo mismo aplica en salud, créditos y educación.\n"
            "Cierre: ¿Te revisamos qué categoría tienes para ver exactamente cuánto pagarías por el servicio que te interesa?\n\n"
            "Objeción: No sé si lo usaré mucho\n"
            "Respuesta: Comfaguajira es un beneficio de tu empleo — ya estás afiliado si tu empresa paga aportes. "
            "No tienes que hacer nada adicional. Solo aprovechar lo que ya está disponible para ti.\n"
            "Cierre: ¿Qué tipo de actividad te gustaría explorar primero — recreación, salud, crédito, educación?\n\n"
            "Objeción: Yo no sabía que tenía este beneficio\n"
            "Respuesta: Es muy común. Muchos trabajadores no saben que su empresa los tiene afiliados. "
            "Con tu cédula podemos verificar tu estado en este momento.\n"
            "Cierre: ¿Me das tu cédula para confirmar si estás activo?\n\n"
            "Objeción: El centro recreativo está lejos\n"
            "Respuesta: Anas Mai está en Riohacha mismo. Maziruma en Dibulla, a menos de 40 minutos. "
            "Los paquetes turísticos incluyen transporte desde el punto de salida.\n"
            "Cierre: ¿Prefieres algo en Riohacha o te animas a salir el fin de semana a Dibulla?"
        ),
    },
    {
        'title': 'Objeciones sobre el crédito social',
        'purpose': 'sales_scripts',
        'content': (
            "Objeción: Los bancos me dan mejor tasa\n"
            "Respuesta: Puede ser, pero el crédito de Comfaguajira no tiene seguro obligatorio caro ni cuota de manejo, "
            "y el descuento va directo por nómina. Para Cat A la tasa es 1.4% mensual, competitiva para crédito de libre inversión.\n"
            "Cierre: ¿Para qué necesitas el crédito? Así te digo cuánto podrías sacar y en cuántas cuotas.\n\n"
            "Objeción: El trámite es muy complicado\n"
            "Respuesta: Es bastante sencillo. Necesitas cédula, certificado laboral y las últimas colillas de pago. "
            "El estudio cuesta $20.000 y la respuesta normalmente es rápida.\n"
            "Cierre: ¿Tienes esos documentos a mano?\n\n"
            "Objeción: Tengo miedo de quedar muy endeudado\n"
            "Respuesta: El estudio analiza tu capacidad de pago real — solo aprueban lo que puedes pagar cómodamente, "
            "y el descuento por nómina hace que ni lo notes mes a mes.\n"
            "Cierre: ¿Quieres que calculemos una cuota aproximada según tu salario?"
        ),
    },
    {
        'title': 'Frases de cierre y activación',
        'purpose': 'sales_scripts',
        'content': (
            "Objeción: Cliente interesado pero no se decide\n"
            "Respuesta: El siguiente paso es muy simple: acércate con tu cédula a cualquier sede de Comfaguajira. "
            "No hay formularios largos ni esperas para empezar a usar recreación o salud.\n"
            "Cierre: ¿Cuándo podrías ir? Te digo la sede más cercana.\n\n"
            "Objeción: Lo pienso y te aviso\n"
            "Respuesta: La disponibilidad en los centros recreativos, especialmente en puentes y festivos, se agota rápido. "
            "Si ya tienes una fecha en mente, conviene reservar con tiempo.\n"
            "Cierre: ¿Tienes algún puente o fin de semana en mente para la visita?\n\n"
            "Objeción: Cliente listo para usar el servicio\n"
            "Respuesta: Perfecto. Para confirmar tu reserva necesitamos: fecha deseada, número de personas y tu cédula o número de afiliado.\n"
            "Cierre: ¿Me das esos datos y revisamos disponibilidad ahora mismo?"
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

print(f"\nTotal: {created} articulos creados")

# Verify
from collections import Counter
counts = Counter(KBArticle.objects.filter(organization=org).values_list('purpose', flat=True))
for purpose, count in sorted(counts.items()):
    print(f"  {purpose}: {count}")
