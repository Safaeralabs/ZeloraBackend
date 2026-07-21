"""
Datos canónicos de los planes comerciales de Zelora (COP, IVA incluido).

Fuente única compartida por el command `seed_plans` y la migración de datos
`0003_seed_plans`. Editar aquí y reejecutar `python manage.py seed_plans`
tras cambiar precios/límites.
"""

SEED_PLANS = [
    {
        'slug': 'emprende',
        'name': 'Emprende',
        'tipo': 'base',
        'price_cop': 69900,
        'annual_price_cop': 699000,
        'price_usd': 17,
        'max_channels': 2,
        'max_agents': 1,
        'max_conversations_month': 200,
        'max_products': 50,
        'extra_conversation_price_cop': 200,
        'trial_days': 7,
        'highlight': False,
        'is_active': True,
        'features': [
            'Mini-tienda + link para bio',
            'Widget para tu web',
            'Voz de tu marca',
            'Nunca inventa · cierra en COP',
            'Foto-IA de producto',
            'Un inbox + handoff a humano',
            'Soporte por correo',
        ],
    },
    {
        'slug': 'crece',
        'name': 'Crece',
        'tipo': 'pro',
        'price_cop': 169900,
        'annual_price_cop': 1699000,
        'price_usd': 41,
        'max_channels': 4,
        'max_agents': 3,
        'max_conversations_month': 1000,
        'max_products': 500,
        'extra_conversation_price_cop': 150,
        'trial_days': 7,
        'highlight': True,
        'is_active': True,
        'features': [
            'Todo lo de Emprende',
            'Seguimiento proactivo',
            'Aprende sola con cada venta',
            'Recomienda y sube el ticket',
            'Analítica completa',
            'Promociones',
            'Soporte prioritario',
            'WhatsApp e Instagram: acceso temprano',
        ],
    },
    {
        'slug': 'negocio',
        'name': 'Negocio',
        'tipo': 'enterprise',
        'price_cop': 399900,
        'annual_price_cop': 3999000,
        'price_usd': 98,
        'max_channels': 6,
        'max_agents': 10,
        'max_conversations_month': 3000,
        'max_products': 0,  # ilimitado
        'extra_conversation_price_cop': 120,
        'trial_days': 7,
        'highlight': False,
        'is_active': True,
        'features': [
            'Todo lo de Crece',
            'WhatsApp + Instagram prioritarios',
            'API y webhooks',
            'Onboarding dedicado',
            'Base de conocimiento a medida',
            'SLA y soporte prioritario',
        ],
    },
]
