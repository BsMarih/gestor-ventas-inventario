from django.db.models import F
from django.urls import reverse

from .models import Element, Sale


def notification_context(request):
    notifications = []

    products_with_low_stock = Element.objects.filter(
        quantity__lte=F("min_quantity")
    ).order_by("quantity", "name")
    for product in products_with_low_stock:
        if product.quantity == 0:
            title = "Producto agotado"
            message = f"{product.name} no tiene unidades disponibles."
        else:
            title = "Stock bajo"
            message = (
                f"{product.name}: quedan {product.quantity} unidades "
                f"(mínimo: {product.min_quantity})."
            )
        notifications.append(
            {
                "title": title,
                "message": message,
                "url": reverse("detail", args=[product.pk]),
                "level": "warning",
            }
        )

    recent_sales = Sale.objects.select_related("element").order_by("-date", "-pk")[:5]
    for sale in recent_sales:
        unit_label = "unidad" if sale.quantity == 1 else "unidades"
        notifications.append(
            {
                "title": "Venta registrada",
                "message": (
                    f"Se vendieron {sale.quantity} {unit_label} de "
                    f"{sale.element.name}."
                ),
                "url": reverse("sales"),
                "level": "sale",
            }
        )
  

    return {
        "notifications": notifications,
        "notification_count": len(notifications),
    }
