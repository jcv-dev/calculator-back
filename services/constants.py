SERVICE_TYPES = {
    "domicilios": {
        "label": "Domicilios",
        "description": "Entrega de comida y pedidos de restaurantes",
        "has_coords": True,
        "default_price": 0,
    },
    "mensajeria": {
        "label": "Mensajería",
        "description": "Envío de paquetes y documentos",
        "has_coords": True,
        "default_price": 0,
    },
    "tramites": {
        "label": "Trámites y Favores",
        "description": "Gestiones y diligencias varias",
        "has_coords": True,
        "default_price": 0,
    },
    "purchases": {
        "label": "Compras",
        "description": "Compras y encargos de cualquier tipo",
        "has_coords": False,
        "default_price": 8000,
    },
    "bancarios": {
        "label": "Trámites Bancarios",
        "description": "Pago de servicios y depósitos sin efectivo",
        "has_coords": False,
        "default_price": 5000,
    },
    "domii_fijo": {
        "label": "Domii Fijo",
        "description": "Domiciliario dedicado por horas",
        "has_coords": False,
        "default_price": 0,
    },
}
