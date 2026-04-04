from apps.accounts.models import Organization
from apps.flows.models import Flow
from apps.flows.serializers import pack_flow_nodes


def _flow(name, description, intent, keywords, nodes, edges, channels=None):
    channels = channels or ['whatsapp', 'web', 'app']
    return {
        'name': name,
        'description': description,
        'trigger': intent,
        'channel': channels[0],
        'is_active': True,
        'nodes': pack_flow_nodes(
            nodes,
            {
                'triggerType': 'hybrid',
                'intent': intent,
                'keywords': keywords,
                'confidenceThreshold': 0.78,
                'fallbackAction': 'request_clarification',
            },
            channels,
        ),
        'edges': edges,
    }


FLOWS = [
    _flow(
        'Validar afiliacion y categoria',
        'Califica al usuario antes de cotizar segun afiliacion, categoria o tipo de cliente.',
        'comfaguajira_affiliation_check',
        ['afiliado', 'categoria', 'subsidio', 'precio', 'tarifa'],
        [
            {'id': 'n1', 'tipo': 'start', 'label': 'Inicio', 'x': 120, 'y': 80},
            {'id': 'n2', 'tipo': 'message', 'label': 'Contexto', 'contenido': 'Antes de darte el valor exacto, validemos si eres afiliado, empresa afiliada o particular.', 'x': 120, 'y': 200},
            {'id': 'n3', 'tipo': 'quickReply', 'label': 'Tipo de cliente', 'opciones': ['Afiliado', 'Empresa afiliada', 'Particular'], 'x': 120, 'y': 340},
            {'id': 'n4', 'tipo': 'collect', 'label': 'Categoria', 'pregunta': 'Si eres afiliado, sabes si tu categoria es A, B o C?', 'variable': 'affiliate_category', 'x': 120, 'y': 500},
            {'id': 'n5', 'tipo': 'message', 'label': 'Cierre', 'contenido': 'Perfecto. Con eso ya te oriento con tarifa, subsidio y condiciones segun tu caso.', 'x': 120, 'y': 660},
            {'id': 'n6', 'tipo': 'end', 'label': 'Fin', 'x': 120, 'y': 820},
        ],
        [
            {'id': 'e1', 'source': 'n1', 'target': 'n2'},
            {'id': 'e2', 'source': 'n2', 'target': 'n3'},
            {'id': 'e3', 'source': 'n3', 'target': 'n4', 'label': 'Afiliado'},
            {'id': 'e4', 'source': 'n3', 'target': 'n5', 'label': 'Empresa o particular'},
            {'id': 'e5', 'source': 'n4', 'target': 'n5'},
            {'id': 'e6', 'source': 'n5', 'target': 'n6'},
        ],
    ),
    _flow(
        'Cotizar nutricion Crecer Sano',
        'Recoge edad, afiliacion y si busca consulta o formulas antes de orientar tarifa y subsidio.',
        'comfaguajira_nutrition_quote',
        ['nutricion', 'crecer sano', 'formula lactea', 'consulta nutricional'],
        [
            {'id': 'n1', 'tipo': 'start', 'label': 'Inicio', 'x': 120, 'y': 80},
            {'id': 'n2', 'tipo': 'collect', 'label': 'Edad del menor', 'pregunta': 'Que edad tiene el nino o nina?', 'variable': 'child_age', 'x': 120, 'y': 220},
            {'id': 'n3', 'tipo': 'quickReply', 'label': 'Interes principal', 'opciones': ['Consulta', 'Formula lactea', 'Ambos'], 'x': 120, 'y': 380},
            {'id': 'n4', 'tipo': 'message', 'label': 'Subsidio', 'contenido': 'Si eres afiliado categoria A o B, la consulta puede quedar en $13.000 y las formulas pueden tener subsidio hasta del 75%.', 'x': 120, 'y': 540},
            {'id': 'n5', 'tipo': 'end', 'label': 'Fin', 'x': 120, 'y': 700},
        ],
        [
            {'id': 'e1', 'source': 'n1', 'target': 'n2'},
            {'id': 'e2', 'source': 'n2', 'target': 'n3'},
            {'id': 'e3', 'source': 'n3', 'target': 'n4'},
            {'id': 'e4', 'source': 'n4', 'target': 'n5'},
        ],
    ),
    _flow(
        'Cotizar educacion',
        'Distingue entre educacion informal, tecnica o formal y captura duracion o programa.',
        'comfaguajira_education_quote',
        ['educacion', 'curso', 'diplomado', 'tecnico', 'colegio'],
        [
            {'id': 'n1', 'tipo': 'start', 'label': 'Inicio', 'x': 120, 'y': 80},
            {'id': 'n2', 'tipo': 'quickReply', 'label': 'Linea educativa', 'opciones': ['Informal', 'Tecnica', 'Formal'], 'x': 120, 'y': 220},
            {'id': 'n3', 'tipo': 'collect', 'label': 'Programa o duracion', 'pregunta': 'Que programa, nivel o duracion te interesa?', 'variable': 'education_need', 'x': 120, 'y': 380},
            {'id': 'n4', 'tipo': 'message', 'label': 'Aclaracion', 'contenido': 'Las tarifas cambian por categoria y tambien pueden existir costos adicionales como inscripcion, certificados o derechos de grado.', 'x': 120, 'y': 540},
            {'id': 'n5', 'tipo': 'end', 'label': 'Fin', 'x': 120, 'y': 700},
        ],
        [
            {'id': 'e1', 'source': 'n1', 'target': 'n2'},
            {'id': 'e2', 'source': 'n2', 'target': 'n3'},
            {'id': 'e3', 'source': 'n3', 'target': 'n4'},
            {'id': 'e4', 'source': 'n4', 'target': 'n5'},
        ],
    ),
    _flow(
        'Reservar espacio',
        'Califica tipo de espacio, duracion y tipo de cliente antes de cotizar.',
        'comfaguajira_space_booking',
        ['alquiler', 'espacio', 'auditorio', 'aula', 'patio de tertulias'],
        [
            {'id': 'n1', 'tipo': 'start', 'label': 'Inicio', 'x': 120, 'y': 80},
            {'id': 'n2', 'tipo': 'quickReply', 'label': 'Espacio', 'opciones': ['Aula', 'Auditorio', 'Patio de tertulias'], 'x': 120, 'y': 220},
            {'id': 'n3', 'tipo': 'quickReply', 'label': 'Duracion', 'opciones': ['4 horas', '8 horas'], 'x': 120, 'y': 380},
            {'id': 'n4', 'tipo': 'message', 'label': 'Condiciones', 'contenido': 'Para tarifa de afiliado puede pedirse cedula y si es empresa afiliada debe estar al dia en aportes.', 'x': 120, 'y': 540},
            {'id': 'n5', 'tipo': 'end', 'label': 'Fin', 'x': 120, 'y': 700},
        ],
        [
            {'id': 'e1', 'source': 'n1', 'target': 'n2'},
            {'id': 'e2', 'source': 'n2', 'target': 'n3'},
            {'id': 'e3', 'source': 'n3', 'target': 'n4'},
            {'id': 'e4', 'source': 'n4', 'target': 'n5'},
        ],
    ),
    _flow(
        'Reservar teatro Akuaipaa',
        'Captura tipo de evento, horario y duracion, y recuerda el anticipo del 50%.',
        'comfaguajira_theater_booking',
        ['teatro', 'akuaipaa', 'evento cultural', 'evento empresarial'],
        [
            {'id': 'n1', 'tipo': 'start', 'label': 'Inicio', 'x': 120, 'y': 80},
            {'id': 'n2', 'tipo': 'collect', 'label': 'Tipo de evento', 'pregunta': 'Que tipo de evento vas a realizar: educativo, cultural, empresarial o comercial?', 'variable': 'event_type', 'x': 120, 'y': 220},
            {'id': 'n3', 'tipo': 'quickReply', 'label': 'Horario', 'opciones': ['Diurno', 'Nocturno'], 'x': 120, 'y': 380},
            {'id': 'n4', 'tipo': 'quickReply', 'label': 'Duracion', 'opciones': ['4 horas', '6 horas', '8 horas'], 'x': 120, 'y': 540},
            {'id': 'n5', 'tipo': 'message', 'label': 'Condiciones', 'contenido': 'La reserva requiere 50% de pago. No se permiten alimentos y el tiempo adicional se cobra.', 'x': 120, 'y': 700},
            {'id': 'n6', 'tipo': 'end', 'label': 'Fin', 'x': 120, 'y': 860},
        ],
        [
            {'id': 'e1', 'source': 'n1', 'target': 'n2'},
            {'id': 'e2', 'source': 'n2', 'target': 'n3'},
            {'id': 'e3', 'source': 'n3', 'target': 'n4'},
            {'id': 'e4', 'source': 'n4', 'target': 'n5'},
            {'id': 'e5', 'source': 'n5', 'target': 'n6'},
        ],
    ),
]


def run():
    org = Organization.objects.get(slug='comfaguajira')
    created = 0
    updated = 0
    for payload in FLOWS:
        _, was_created = Flow.objects.update_or_create(
            organization=org,
            name=payload['name'],
            defaults=payload,
        )
        if was_created:
            created += 1
        else:
            updated += 1
    print(f'Flows Comfaguajira: {created} creados, {updated} actualizados')


if __name__ == '__main__':
    run()
