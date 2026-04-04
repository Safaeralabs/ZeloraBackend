from django.contrib.auth import get_user_model
from django.db import connection

from apps.accounts.models import Organization
from apps.channels_config.models import ChannelConfig
from apps.knowledge_base.models import KBArticle
from apps.ecommerce.models import Product, ProductVariant


User = get_user_model()


def table_exists(name: str) -> bool:
    with connection.cursor() as cursor:
        rows = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=%s",
            [name],
        ).fetchall()
    return bool(rows)


org_slug = "valdiri-move-demo"
org_name = "Valdiri Move Demo"
admin_email = "admin@valdirimove.com"
admin_password = "Admin1234!"


org, _ = Organization.objects.update_or_create(
    slug=org_slug,
    defaults={
        "name": org_name,
        "industry": "Moda y fitness",
        "country": "Colombia",
        "website": "https://valdirimove.co",
        "plan": "pro",
        "max_agents": 8,
        "monthly_message_limit": 10000,
        "timezone": "America/Bogota",
        "is_active": True,
    },
)

admin, _ = User.objects.get_or_create(
    email=admin_email,
    defaults={
        "organization": org,
        "nombre": "Admin",
        "apellido": "Valdiri Move",
        "rol": "admin",
        "is_staff": True,
        "is_available": True,
        "is_active": True,
    },
)
admin.organization = org
admin.nombre = "Admin"
admin.apellido = "Valdiri Move"
admin.rol = "admin"
admin.is_staff = True
admin.is_active = True
admin.is_available = True
admin.set_password(admin_password)
admin.save()

asesor, _ = User.objects.get_or_create(
    email="asesor1@valdirimove.com",
    defaults={
        "organization": org,
        "nombre": "Sara",
        "apellido": "Mendoza",
        "rol": "asesor",
        "is_active": True,
        "is_available": True,
    },
)
asesor.organization = org
asesor.nombre = "Sara"
asesor.apellido = "Mendoza"
asesor.rol = "asesor"
asesor.is_active = True
asesor.is_available = True
asesor.set_password("Asesor1234!")
asesor.save()

onboarding_settings = {
    "organization_name": org_name,
    "website": "https://valdirimove.co",
    "timezone": "America/Bogota",
    "tax_id": "901845221-1",
    "contact_email": "hola@valdirimove.co",
    "contact_phone": "+57 300 555 0198",
    "what_you_sell": "ropa deportiva femenina, sets de entrenamiento, leggings, tops, enterizos y accesorios fitness de uso diario",
    "who_you_sell_to": "mujeres de 18 a 35 anos en Colombia, especialmente en Barranquilla, que quieren verse bien, entrenar comodas y comprar por chat sin complicarse",
    "quick_knowledge_text": "Marca barranquillera inspirada en una creadora de lifestyle y fitness. Venta conversacional de ropa deportiva fisica con enfoque en fit, comodidad, envio rapido y look favorecedor.",
    "quick_knowledge_links": ["https://instagram.com/andreavaldirisos"],
    "quick_knowledge_files": [],
    "activation_tasks": {
        "knowledge_status": "completed",
        "channels_status": "completed",
        "agent_test_status": "completed",
        "agent_tested_at": None,
    },
    "initial_onboarding_completed": True,
    "brand_profile": {
        "tone_of_voice": "cercano, seguro y femenino",
        "formality_level": "balanced",
        "brand_personality": "segura, costeña, directa, aspiracional y con energia",
        "value_proposition": "Ropa deportiva que estiliza, se siente comoda y funciona tanto para entrenar como para verte bien en el dia a dia.",
        "key_differentiators": [
            "Tela gruesa que no transparenta",
            "Molderia que estiliza cintura y gluteo",
            "Sets pensados para clima calido como Barranquilla",
            "Asesoria rapida por chat para talla y combinaciones",
        ],
        "preferred_closing_style": "directo",
        "urgency_style": "soft",
        "recommended_phrases": [
            "te queda brutal",
            "si quieres te digo cual te conviene mas",
            "te recomiendo irte por esta opcion",
            "si te gusta, te la dejo lista",
        ],
        "avoid_phrases": [
            "con gusto",
            "estoy aqui para ayudarte",
            "la mejor opcion para tu caso",
            "si gustas",
        ],
    },
    "sales_playbook": {
        "opening_style": "Entrar directo, leer rapido la necesidad y evitar saludos roboticos si la conversacion ya arranco.",
        "recommendation_style": "Recomendar maximo 2 opciones, explicar fit, tela, uso y por que encaja.",
        "objection_style": "Responder corto, con seguridad y llevando la conversacion a una decision.",
        "closing_style": "Cerrar con pregunta concreta tipo talla, color o envio para avanzar a pedido.",
        "follow_up_style": "Seguimiento suave, una sola pregunta util y sin acosar.",
        "upsell_style": "Si compra set, sugerir una banda o scrunchie; si compra legging, sugerir top a juego.",
        "escalate_conditions": ["pedido corporativo", "mas de 12 unidades", "cambio especial no publicado"],
    },
    "buyer_model": {
        "ideal_buyers": ["mujeres activas", "clientes que entrenan 3+ veces por semana", "compradoras que quieren verse estilizadas"],
        "common_objections": ["no se si la tela transparenta", "no se que talla pedir", "me preocupa que caliente mucho", "quiero algo que me horme bonito"],
        "purchase_signals": ["cuanto cuesta", "que talla me recomiendas", "tienen envio hoy", "lo quiero", "como hago el pedido"],
        "low_intent_signals": ["lo voy a pensar", "despues te escribo", "solo estoy mirando"],
        "bulk_buyer_signals": ["quiero varias para mi equipo", "necesito uniformes", "somos un grupo grande"],
    },
    "commerce_rules": {
        "discount_policy": "Solo se ofrecen descuentos o promos activas publicadas.",
        "negotiation_policy": "No negociar precios individuales por chat salvo autorizacion humana.",
        "inventory_promise_rule": "No prometer stock sin validar variante y talla.",
        "delivery_promise_rule": "Barranquilla y area metropolitana 24 a 48 horas habiles; resto del pais 2 a 5 dias habiles.",
        "return_policy_summary": "Cambios por talla dentro de 5 dias calendario si la prenda esta sin uso, con etiquetas y sujeto a disponibilidad.",
        "forbidden_claims": ["decir que una talla le sirve a todo el mundo", "prometer efecto moldeador medico", "decir que una promo aplica si no existe"],
        "forbidden_promises": ["apartar sin pago", "entrega el mismo dia sin confirmarlo", "cambios en prendas usadas"],
    },
    "locale_settings": {
        "language": "es",
        "date_format": "DD/MM/YYYY",
        "default_response_language": True,
        "session_timeout_minutes": 480,
    },
    "notification_settings": {
        "items": [
            {"key": "nueva_conv", "label": "Nueva conversacion entrante", "email": True, "whatsapp": False, "browser": True, "enabled": True},
            {"key": "escalada", "label": "Conversacion escalada", "email": True, "whatsapp": True, "browser": True, "enabled": True},
        ],
    },
    "ai_preferences": {
        "provider": "openai",
        "copilot_model": "gpt-4o",
        "summary_model": "gpt-4.1-nano",
        "temperature": 0.55,
        "max_tokens": 350,
        "confidence_threshold": 75,
        "copilot_suggestions": 3,
        "sentiment_analysis": True,
        "auto_summary": True,
        "qa_scoring": True,
        "sales_agent": {
            "enabled": True,
            "autonomy_level": "semi_autonomo",
            "followup_mode": "suave",
            "max_followups": 1,
            "recommendation_depth": 2,
            "handoff_mode": "balanceado",
        },
    },
    "optimization_profile": {
        "status": "ready_for_testing",
        "last_updated_at": None,
    },
    "onboarding_status": "completed",
    "completed_step": 3,
}

ChannelConfig.objects.update_or_create(
    organization=org,
    channel="onboarding",
    defaults={"is_active": True, "settings": onboarding_settings},
)

ChannelConfig.objects.update_or_create(
    organization=org,
    channel="app",
    defaults={
        "is_active": True,
        "settings": {
            "app_name": "Valdiri Move",
            "welcome_message": "Hola, soy el asesor de Valdiri Move. Si quieres, te ayudo a elegir set, talla o color rapido.",
            "primary_color": "#f25d8e",
            "accent_color": "#321b2f",
            "background_image_url": "",
            "background_overlay": "soft-dark",
            "font_family": "Manrope",
            "font_scale": "md",
            "presentation_style": "bottom_sheet",
            "surface_style": "glass",
            "bubble_style": "rounded",
            "user_bubble_color": "#f25d8e",
            "agent_bubble_color": "#fff8fb",
            "header_logo_url": "",
            "launcher_label": "Comprar por chat",
            "ios_bundle_ids": ["co.valdirimove.app"],
            "android_package_names": ["co.valdirimove.app"],
            "allowed_origins": ["http://localhost:5173"],
            "auth_mode": "session",
            "require_authentication": False,
            "push_enabled": False,
            "handoff_enabled": True,
            "install_status": "installed",
            "verified_apps": ["co.valdirimove.app"],
        },
    },
)

ChannelConfig.objects.update_or_create(
    organization=org,
    channel="web",
    defaults={
        "is_active": True,
        "settings": {
            "widget_name": "Valdiri Move Web Chat",
            "greeting_message": "Hola, te ayudo con sets, tallas, envios y promos de Valdiri Move.",
            "brand_color": "#f25d8e",
            "position": "bottom-right",
            "allowed_domains": ["localhost"],
            "launcher_label": "Comprar ahora",
            "require_consent": True,
            "handoff_enabled": True,
            "install_status": "installed",
            "verified_domains": ["localhost"],
        },
    },
)

articles = [
    (
        "Guia de tallas Valdiri Move",
        "Tallas",
        ["tallas", "legging", "top", "fit"],
        "Talla S: cintura 62-70 cm, cadera 88-96 cm, busto 82-88 cm. Talla M: cintura 70-78 cm, cadera 96-104 cm, busto 88-94 cm. Talla L: cintura 78-86 cm, cadera 104-112 cm, busto 94-100 cm. Si la clienta esta entre dos tallas y quiere mas compresion, sugerir la menor solo si normalmente tolera fit ajustado. Si prefiere comodidad, subir una talla. Los tops tienen soporte medio. Los leggings tallan fiel.",
    ),
    (
        "Politicas de cambios y devoluciones",
        "Politicas",
        ["cambios", "devoluciones", "garantia"],
        "Se permiten cambios por talla dentro de 5 dias calendario desde la entrega. La prenda debe estar sin uso, limpia, con etiquetas y empaque. No se aceptan cambios de prendas usadas, con olor a perfume o sin etiquetas. Si la talla deseada no esta disponible, se ofrece bono por el valor pagado para otra referencia. No hay devolucion de dinero en prendas promocionales salvo error de fabrica.",
    ),
    (
        "Envios y tiempos de entrega",
        "Envios",
        ["envio", "entrega", "barranquilla"],
        "Barranquilla y area metropolitana: 24 a 48 horas habiles despues de confirmado el pago. Ciudades principales de Colombia: 2 a 5 dias habiles. Los sabados cuentan como dia operativo parcial. Si el pedido entra despues de las 3 pm, empieza a contar al siguiente dia habil. No prometer entrega el mismo dia si no esta confirmada por operaciones.",
    ),
    (
        "Cuidados de las prendas",
        "Producto",
        ["cuidado", "tela", "lavado"],
        "Lavar a mano o en ciclo delicado con agua fria. No usar blanqueador. No secar al sol intenso por tiempos prolongados. No planchar directamente sobre zonas de compresion ni estampados. Esto ayuda a mantener color, ajuste y elasticidad.",
    ),
    (
        "FAQ comercial y objeciones frecuentes",
        "Ventas",
        ["faq", "objeciones", "venta"],
        "Si preguntan si transparenta: responder que la tela es de alta cobertura y la mayoria de clientas la eligen por eso, pero siempre es mejor usar la talla correcta. Si dudan por el calor: explicar que las telas fueron pensadas para clima calido y entrenamiento ligero a medio. Si preguntan cual horma mas: recomendar Power Sculpt para definir cintura y gluteo. Si estan indecisas, cerrar con una sola pregunta concreta sobre uso, talla o presupuesto.",
    ),
]

for title, category, tags, content in articles:
    KBArticle.objects.update_or_create(
        organization=org,
        title=title,
        defaults={
            "author": admin,
            "content": content,
            "category": category,
            "tags": tags,
            "status": "published",
            "is_active": True,
        },
    )

products = [
    {
        "title": "Set Power Sculpt Rosado",
        "brand": "Valdiri Move",
        "category": "Ropa deportiva",
        "description": "Set fisico de top y legging de compresion media, cintura alta y tela gruesa que estiliza sin transparentar.",
        "fulfillment_notes": "Ideal para entrenamiento, caminata y uso diario. Despacho nacional.",
        "tags": ["set", "legging", "top", "rosado", "best seller"],
        "variants": [("VM-PSR-S", "Talla S", 189900, 12), ("VM-PSR-M", "Talla M", 189900, 9), ("VM-PSR-L", "Talla L", 189900, 6)],
    },
    {
        "title": "Legging Heat Control Negro",
        "brand": "Valdiri Move",
        "category": "Leggings",
        "description": "Legging fisico cintura alta con tela suave de secado rapido, pensado para clima calido y look estilizado.",
        "fulfillment_notes": "Prenda fisica con envio. Combina con tops de alto soporte.",
        "tags": ["legging", "negro", "cintura alta"],
        "variants": [("VM-HCN-S", "Talla S", 119900, 14), ("VM-HCN-M", "Talla M", 119900, 11), ("VM-HCN-L", "Talla L", 119900, 8)],
    },
    {
        "title": "Top Motion Support Arena",
        "brand": "Valdiri Move",
        "category": "Tops deportivos",
        "description": "Top fisico de soporte medio con espalda limpia y horma comoda para entrenamiento y outfits athleisure.",
        "fulfillment_notes": "Ideal para combinar con leggings lisos o sets tono neutro.",
        "tags": ["top", "arena", "soporte medio"],
        "variants": [("VM-MSA-S", "Talla S", 79900, 10), ("VM-MSA-M", "Talla M", 79900, 10), ("VM-MSA-L", "Talla L", 79900, 5)],
    },
    {
        "title": "Enterizo Shape Black",
        "brand": "Valdiri Move",
        "category": "Enterizos",
        "description": "Enterizo fisico moldeador de fit ajustado, escote deportivo y tela premium de alta cobertura.",
        "fulfillment_notes": "Pieza statement para entrenar o usar con sobrecamisa.",
        "tags": ["enterizo", "premium", "negro"],
        "variants": [("VM-ESB-S", "Talla S", 169900, 7), ("VM-ESB-M", "Talla M", 169900, 5), ("VM-ESB-L", "Talla L", 169900, 4)],
    },
    {
        "title": "Scrunchie Move Pack x3",
        "brand": "Valdiri Move",
        "category": "Accesorios",
        "description": "Pack fisico de scrunchies suaves para complementar looks deportivos y sumar ticket en compra por chat.",
        "fulfillment_notes": "Upsell natural para cualquier pedido de ropa.",
        "tags": ["accesorios", "scrunchie", "upsell"],
        "variants": [("VM-SCR-3", "Pack unico", 29900, 20)],
    },
]

for item in products:
    product, _ = Product.objects.update_or_create(
        organization=org,
        title=item["title"],
        defaults={
            "brand": item["brand"],
            "description": item["description"],
            "category": item["category"],
            "offer_type": "physical",
            "price_type": "fixed",
            "service_mode": "not_applicable",
            "requires_booking": False,
            "requires_shipping": True,
            "service_duration_minutes": 0,
            "capacity": 0,
            "fulfillment_notes": item["fulfillment_notes"],
            "attributes": {},
            "status": "active",
            "images": [],
            "tags": item["tags"],
            "is_active": True,
        },
    )
    existing = set(product.variants.values_list("sku", flat=True))
    incoming = set()
    for sku, name, price, stock in item["variants"]:
        incoming.add(sku)
        ProductVariant.objects.update_or_create(
            product=product,
            sku=sku,
            defaults={
                "name": name,
                "price": price,
                "cost": round(price * 0.48, 2),
                "stock": stock,
                "reserved": 0,
                "duration_minutes": 0,
                "capacity": 0,
                "delivery_mode": "shipping",
                "metadata": {"demo_seed": True},
            },
        )
    for sku in existing - incoming:
        product.variants.filter(sku=sku).delete()

if table_exists("ai_agents"):
    from apps.ai_engine.models import AIAgent

    for agent_type, name, active, provider, model in [
        ("sales", "Sales Agent", True, "openai", "gpt-4o"),
        ("marketing", "Marketing Agent", False, "openai", "gpt-4.1-nano"),
        ("operations", "Operations Agent", False, "openai", "gpt-4.1-nano"),
    ]:
        AIAgent.objects.update_or_create(
            organization=org,
            agent_type=agent_type,
            defaults={
                "name": name,
                "is_active": active,
                "provider": provider,
                "model": model,
                "tools": ["catalog", "knowledge_base", "orders"] if agent_type == "sales" else [],
                "config": {"demo_seed": True},
            },
        )

print(
    {
        "organization": org.name,
        "slug": org.slug,
        "admin_email": admin.email,
        "admin_password": admin_password,
        "agent_email": asesor.email,
        "agent_password": "Asesor1234!",
        "products": Product.objects.filter(organization=org, is_active=True).count(),
        "kb_articles": KBArticle.objects.filter(organization=org, is_active=True).count(),
        "public_appchat_url": f"http://localhost:5173/{org.slug}/",
    }
)
