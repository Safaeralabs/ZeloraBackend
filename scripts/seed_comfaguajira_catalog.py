from decimal import Decimal

from apps.accounts.models import Organization
from apps.ecommerce.models import Product, ProductVariant


CATALOG = [
    {
        "title": "Credito social Comfaguajira",
        "category": "Creditos",
        "description": "Linea de credito social para salud, recreacion, turismo, educacion, libre inversion y compra de cartera.",
        "price_type": "variable",
        "base_price": Decimal("20000"),
        "fulfillment_notes": "Modalidades por libranza o pignoracion. Estudio de credito incluido como costo inicial.",
        "tags": ["credito", "financiacion", "salud", "educacion", "turismo"],
        "attributes": {
            "plazos": "36 a 60 meses",
            "tasas": {
                "categoria_a": "1.3% a 1.4%",
                "categoria_b": "1.4% a 1.5%",
                "categoria_c": "hasta 1.6%",
            },
            "modalidades": ["libranza", "pignoracion"],
            "estudio_credito": "$20.000",
        },
        "variants": [
            ("SALUD", "Credito Salud", Decimal("20000")),
            ("RECREACION", "Credito Recreacion", Decimal("20000")),
            ("TURISMO", "Credito Turismo", Decimal("20000")),
            ("EDUCACION", "Credito Educacion", Decimal("20000")),
            ("LIBRE", "Credito Libre inversion", Decimal("20000")),
            ("CARTERA", "Compra de cartera", Decimal("20000")),
        ],
    },
    {
        "title": "Programa de nutricion Crecer Sano",
        "category": "Subsidios y nutricion",
        "description": "Programa para ninos de 6 meses a 14 anos con consulta nutricional y formulas lacteas subsidiadas.",
        "price_type": "fixed",
        "base_price": Decimal("13000"),
        "fulfillment_notes": "Aplica subsidio para afiliados categoria A y B. Paquetes disponibles de 2, 3 o 5 unidades.",
        "tags": ["nutricion", "subsidio", "infantil", "formula lactea"],
        "attributes": {
            "consulta_general": "$35.324",
            "consulta_subsidiada_ab": "$13.000",
            "subsidio_formulas": "Hasta 75%",
            "formulas_rango": "$32.900 a mas de $300.000",
            "edades": "6 meses a 14 anos",
        },
        "variants": [
            ("CONSULTA", "Consulta nutricional subsidiada", Decimal("13000")),
            ("FORMULA-2", "Paquete formula lactea x2", Decimal("32900")),
            ("FORMULA-3", "Paquete formula lactea x3", Decimal("48900")),
            ("FORMULA-5", "Paquete formula lactea x5", Decimal("81500")),
        ],
    },
    {
        "title": "Educacion informal",
        "category": "Educacion",
        "description": "Talleres, seminarios, cursos, cursos productivos, diplomados y congresos con tematicas segun demanda.",
        "price_type": "fixed",
        "base_price": Decimal("0"),
        "fulfillment_notes": "Incluye docente, salon y en algunos casos refrigerio. Capacidad maxima de 25 a 30 personas.",
        "tags": ["educacion", "talleres", "seminarios", "diplomados"],
        "attributes": {
            "capacidad": "25 a 30 personas",
            "incluye": ["docente", "salon", "refrigerio en algunos casos"],
        },
        "variants": [
            ("TALLER1", "Taller 1 hora", Decimal("0")),
            ("TALLER4", "Taller 4 horas", Decimal("25200")),
            ("SEMINARIO8", "Seminario 8 horas", Decimal("41300")),
            ("CURSO20", "Curso 20 horas", Decimal("98800")),
            ("CURSO40", "Curso 40 horas", Decimal("180600")),
            ("PRODUCTIVO60", "Curso productivo 60 horas", Decimal("226800")),
            ("PRODUCTIVO80", "Curso productivo 80 horas", Decimal("283400")),
            ("DIPLOMADO80", "Diplomado 80 horas", Decimal("586500")),
            ("DIPLOMADO120", "Diplomado 120 horas", Decimal("862000")),
            ("DIPLOMADO230", "Diplomado 230 horas", Decimal("1425400")),
            ("CONGRESO20", "Congreso nacional 20 horas", Decimal("432500")),
        ],
    },
    {
        "title": "Formacion laboral tecnica",
        "category": "Educacion tecnica",
        "description": "Tecnicos laborales, diplomados tecnicos y seminarios de profundizacion o emprendimiento.",
        "price_type": "fixed",
        "base_price": Decimal("91200"),
        "fulfillment_notes": "Pago trimestral o semestral. Requiere inscripcion previa.",
        "tags": ["tecnico", "formacion laboral", "seminarios", "emprendimiento"],
        "attributes": {
            "duracion": "600 a 1200 horas",
            "inscripcion": "Desde $24.900",
            "certificados": "Desde $15.400",
            "derecho_grado": "Desde $355.400",
        },
        "variants": [
            ("SEMESTRE", "Semestre tecnico", Decimal("182400")),
            ("TRIMESTRE", "Pago trimestral tecnico", Decimal("91200")),
            ("DIPLOMADO80", "Diplomado tecnico 80 horas", Decimal("129500")),
            ("DIPLOMADO120", "Diplomado tecnico 120 horas", Decimal("183100")),
            ("SEMINARIO", "Seminario de profundizacion", Decimal("10200")),
        ],
    },
    {
        "title": "Educacion formal Colegio Comfaguajira",
        "category": "Educacion formal",
        "description": "Oferta academica en preescolar, primaria y secundaria.",
        "price_type": "fixed",
        "base_price": Decimal("112000"),
        "fulfillment_notes": "Tarifas dependen de categoria A, B o C. Pago mensual de pension.",
        "tags": ["colegio", "educacion formal", "matricula", "pension"],
        "attributes": {
            "niveles": ["preescolar", "primaria", "secundaria"],
            "matricula_rango": "$393.400 a $897.000",
            "pension_rango": "$112.000 a $364.000",
        },
        "variants": [
            ("PREESCOLAR", "Preescolar", Decimal("112000")),
            ("PRIMARIA", "Primaria", Decimal("198000")),
            ("SECUNDARIA", "Secundaria", Decimal("364000")),
        ],
    },
    {
        "title": "Alquiler de espacios",
        "category": "Espacios y eventos",
        "description": "Alquiler de aulas, auditorio y patio de tertulias por 4 u 8 horas.",
        "price_type": "fixed",
        "base_price": Decimal("62000"),
        "fulfillment_notes": "Incluye aire acondicionado, sillas, tablero, marcadores, vigilancia e IVA.",
        "tags": ["alquiler", "espacios", "auditorio", "aulas"],
        "attributes": {
            "duraciones": ["4 horas", "8 horas"],
            "condiciones": [
                "Presentar cedula para tarifa de afiliado",
                "Empresas deben estar al dia en aportes",
            ],
        },
        "variants": [
            ("AULA-4", "Aula 4 horas", Decimal("62000")),
            ("AULA-8", "Aula 8 horas", Decimal("124000")),
            ("AUDITORIO-4", "Auditorio 4 horas", Decimal("441000")),
            ("AUDITORIO-8", "Auditorio 8 horas", Decimal("883000")),
        ],
    },
    {
        "title": "Teatro Akuaipaa",
        "category": "Eventos y teatro",
        "description": "Espacio para eventos educativos, culturales, empresariales y comerciales.",
        "price_type": "fixed",
        "base_price": Decimal("1057400"),
        "fulfillment_notes": "Reserva con 50% de pago. Incluye tiempo de montaje. Recargos nocturnos y fines de semana.",
        "tags": ["teatro", "eventos", "cultural", "empresarial"],
        "attributes": {
            "condiciones": [
                "No se permite consumo de alimentos",
                "Tiempo adicional se cobra",
                "Incluye tiempo de montaje",
            ],
        },
        "variants": [
            ("DIA-4", "Teatro 4 horas diurno", Decimal("1057400")),
            ("NOCHE-4", "Teatro 4 horas nocturno", Decimal("1905000")),
            ("DIA-6", "Teatro 6 horas", Decimal("1744800")),
            ("NOCHE-6", "Teatro 6 horas premium", Decimal("3142000")),
            ("DIA-8", "Teatro 8 horas", Decimal("2114800")),
            ("NOCHE-8", "Teatro 8 horas premium", Decimal("3808000")),
        ],
    },
]


def run():
    org = Organization.objects.get(slug="comfaguajira")

    for item in CATALOG:
        product, _ = Product.objects.update_or_create(
            organization=org,
            title=item["title"],
            defaults={
                "brand": "Comfaguajira",
                "description": item["description"],
                "category": item["category"],
                "offer_type": "service",
                "price_type": item["price_type"],
                "service_mode": "onsite",
                "requires_booking": True,
                "requires_shipping": False,
                "fulfillment_notes": item["fulfillment_notes"],
                "attributes": item["attributes"],
                "status": "active",
                "is_active": True,
                "tags": item["tags"],
                "images": [],
            },
        )
        existing = {variant.sku: variant for variant in product.variants.all()}
        seen = set()
        for sku, name, price in item["variants"]:
            ProductVariant.objects.update_or_create(
                product=product,
                sku=sku,
                defaults={
                    "name": name,
                    "price": price,
                    "stock": 999,
                    "reserved": 0,
                    "duration_minutes": 0,
                    "capacity": 0,
                    "delivery_mode": "not_applicable",
                    "metadata": {"base_price": str(item["base_price"])},
                },
            )
            seen.add(sku)
        for sku, variant in existing.items():
            if sku not in seen:
                variant.delete()

    print(f"Catalogo sembrado para {org.slug}: {Product.objects.filter(organization=org).count()} productos")


if __name__ == "__main__":
    run()
