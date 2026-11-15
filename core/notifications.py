from django.db.models import F
from django.urls import reverse

from .models import Element, Sale


DISMISSED_NOTIFICATIONS_SESSION_KEY = "dismissed_notifications"


def get_notifications():
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
                "id": f"stock-{product.pk}",
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
                "id": f"sale-{sale.pk}",
            }
        )

    return notifications


def notification_context(request):
    notifications = get_notifications()
    active_ids = {notification["id"] for notification in notifications}
    dismissed_ids = set(
        request.session.get(DISMISSED_NOTIFICATIONS_SESSION_KEY, [])
    )
    valid_dismissed_ids = dismissed_ids & active_ids
    if valid_dismissed_ids != dismissed_ids:
        request.session[DISMISSED_NOTIFICATIONS_SESSION_KEY] = sorted(
            valid_dismissed_ids
        )

    notifications = [
        notification
        for notification in notifications
        if notification["id"] not in valid_dismissed_ids
    ]
    return {
        "notifications": notifications,
        "notification_count": len(notifications),
    }
