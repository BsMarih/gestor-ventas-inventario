import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.contrib import messages
from django.db import models
from django.shortcuts import get_object_or_404, render,redirect
from django.views.generic import ListView
from django.core.paginator import Paginator
from .forms import CreateElementForm, InventorySettingsForm, SalesForm
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.text import slugify
from django.http import JsonResponse

from .models import Element,Type,Category,InventorySettings,Sale

logger = logging.getLogger(__name__)

# APIs públicas a usar, catálogo limitado 
PRODUCT_CATALOGS = (
    ("Open Food Facts", "https://world.openfoodfacts.org", "Alimentos"),
    ("Open Beauty Facts", "https://world.openbeautyfacts.org", "Higiene y belleza"),
    ("Open Products Facts", "https://world.openproductsfacts.org", "Productos generales"),
)


def lookup_product_catalogs(barcode):
    if not barcode.isascii() or not barcode.isdigit() or not 8 <= len(barcode) <= 14:
        return None, "El código debe tener entre 8 y 14 dígitos."

    fields = (
        "product_name,product_name_es,product_name_en,generic_name,"
        "brands,quantity,categories,categories_hierarchy,code"
    )
    unavailable_catalogs = []

    for catalog_name, catalog_url, default_category in PRODUCT_CATALOGS:
        url = (
            f"{catalog_url}/api/v2/product/{quote(barcode, safe='')}.json"
            f"?fields={fields}"
        )
        request = Request(url, headers={"User-Agent": "GestorVentasInventario/1.0"})

        try:
            with urlopen(request, timeout=5) as response:
                data = json.loads(response.read(1_000_000))
        except (
            HTTPError,
            URLError,
            TimeoutError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as error:
            unavailable_catalogs.append(catalog_name)
            logger.warning(
                "No se pudo consultar %s para el código %s: %s",
                catalog_name,
                barcode,
                error,
            )
            continue

        product = data.get("product") if isinstance(data, dict) else None
        if not isinstance(product, dict) or data.get("status") != 1:
            continue

        categories = product.get("categories_hierarchy") or []
        if not isinstance(categories, list) or not categories:
            categories = [
                category.strip()
                for category in str(product.get("categories", "")).split(",")
                if category.strip()
            ]
        if categories:
            product_type = str(categories[-1]).split(":", 1)[-1].replace("-", " ").strip()
        else:
            product_type = "Producto escaneado"

        description_parts = [
            value
            for value in (
                product.get("generic_name"),
                f"Marca: {product['brands']}" if product.get("brands") else None,
                f"Presentación: {product['quantity']}" if product.get("quantity") else None,
            )
            if value
        ]
        name = (
            product.get("product_name_es")
            or product.get("product_name")
            or product.get("product_name_en")
            or product.get("generic_name")
            or f"Producto {barcode}"
        )

        return {
            "name": str(name)[:255],
            "description": " | ".join(str(part) for part in description_parts)[:2000],
            "category": default_category,
            "type": product_type[:255],
        }, None

    if unavailable_catalogs:
        return None, "No se pudieron consultar todos los catálogos. Puedes completar el producto manualmente."
    return None, "No se encontró el producto en los catálogos consultados. Puedes completar los datos manualmente."


def get_prioritized_elements(replenishment_days=None):
    today = timezone.localdate()
    sales_summary = {
        summary["element_id"]: summary
        for summary in (
            Sale.objects.filter(date__lte=today)
            .values("element_id")
            .annotate(
                units_sold=models.Sum("quantity"),
                sale_count=models.Count("id"),
                first_sale_date=models.Min("date"),
            )
        )
    }

    elements = []
    for element in Element.objects.all().order_by("id"):
        summary = sales_summary.get(element.id)
        element.has_sales_history = summary is not None
        element.has_sales_rate = False
        element.average_daily_sales = None
        element.average_days_between_sales = None
        element.days_until_stockout = None
        element.predicted_stockout = False

        if summary:
            observation_days = max((today - summary["first_sale_date"]).days + 1, 1)
            element.average_daily_sales = summary["units_sold"] / observation_days
            element.average_days_between_sales = observation_days / summary["sale_count"]
            if element.average_daily_sales:
                element.has_sales_rate = True
                element.days_until_stockout = (
                    element.quantity / element.average_daily_sales
                )
                element.predicted_stockout = bool(
                    replenishment_days is not None
                    and element.days_until_stockout <= replenishment_days
                )

        if element.quantity <= element.min_quantity or element.predicted_stockout:
            elements.append(element)

    elements.sort(
        key=lambda element: (
            element.days_until_stockout is None and element.quantity > 0,
            element.days_until_stockout
            if element.days_until_stockout is not None
            else element.quantity,
            element.id,
        )
    )
    return elements


def search_products(product_query):
    if product_query:
        return (
            Element.objects.filter(
                models.Q(name__icontains=product_query)
                | models.Q(barcode__icontains=product_query)
                | models.Q(description__icontains=product_query)
                | models.Q(category__name__icontains=product_query)
                | models.Q(type__name__icontains=product_query)
            )
            .select_related("category", "type")
            .order_by("name", "id")
        )
    return Element.objects.none()


def product_search_context(request):
    return {"product_query": request.GET.get("q", "").strip()}


def product_search(request):
    product_query = request.GET.get("q", "").strip()
    return render(
        request,
        "core/product_search_results.html",
        {
            "product_query": product_query,
            "search_results": search_products(product_query),
            "product_search_enabled": True,
        },
    )


# Create your views here.
def index(request):
    replenishment_settings = InventorySettings.objects.filter(pk=1).first()
    prioritized_products = get_prioritized_elements(
        replenishment_settings.replenishment_days if replenishment_settings else None
    )[:5]
    today = timezone.localdate()
    current_month_sales = Sale.objects.filter(date__year=today.year, date__month=today.month)
    monthly_sales = current_month_sales.aggregate(
        total=models.Sum(models.F("quantity") * models.F("element__price"))
    )["total"] or 0
    sales_quantity = Sale.objects.aggregate(total=models.Sum("quantity"))["total"] or 0
    total_productos = Element.objects.filter(quantity__gt=0).count()

    return render(
        request,
        "core/index.html",
        {
            "prioritized_products": prioritized_products,
            "monthly_sales": monthly_sales,
            "total_productos": total_productos,
            "sales_quantity": sales_quantity,
            "product_search_enabled": True,
            **product_search_context(request),
        },
    )

# vista que muestra detalles de productos
def detail(request,pk):
    element = get_object_or_404(Element, pk=pk)
    recent_sales = element.sales.order_by("-date", "-id")[:10]
    return render(
        request,
        "core/detail.html",
        {"element": element, "recent_sales": recent_sales},
    )

def get_types(request):
    category_name = request.GET.get('category')
    try:
        category = Category.objects.get(name=category_name)
        types = list(Type.objects.filter(category=category).values_list('name', flat=True))
    except Category.DoesNotExist:
        types = []

    return JsonResponse(types, safe=False)


def product_scan(request):
    return render(request, "core/product_scan.html")


def inventory(request):
    elements = Element.objects.all().order_by('-id')

    paginator = Paginator(elements, 10)
    page_number = request.GET.get('page')
    elements_page = paginator.get_page(page_number)

    return render(
        request,
        "core/inventory.html",
        {
            "elements": elements_page,
            "product_search_enabled": True,
            **product_search_context(request),
        },
    )

# agregar productos al inventario
def create_element(request):
    if request.method == "POST":
        form = CreateElementForm(request.POST)

        if form.is_valid():
            category_name = form.cleaned_data.pop("category").strip()
            type_name = form.cleaned_data.pop("type").strip()

            category, _ = Category.objects.get_or_create(name=category_name, defaults={"slug": slugify(category_name)})
            type_obj, _ = Type.objects.get_or_create(
                name=type_name,
                category=category,
                defaults={"slug": f"{category.slug}-{slugify(type_name)}"},
            )
            element = form.save(commit=False)

            element.category = category
            element.type = type_obj

            element.slug = slugify(element.name)

            element.save()

            return redirect("inventory")
        else:
            print(form.errors)

    else:
        initial = {}
        scan_message = None
        barcode = request.GET.get("barcode", "").strip()
        if barcode:
            initial["barcode"] = barcode
            product_data, scan_message = lookup_product_catalogs(barcode)
            if product_data:
                initial.update(product_data)
                scan_message = "Producto encontrado. Revisa o completa los datos antes de guardar."

        form = CreateElementForm(initial=initial)

    context = {
        "form": form,
        "categories": Category.objects.all(),
        "types": Type.objects.all(),
        "scan_message": scan_message if request.method == "GET" else None,
    }

    return render(request,"core/create_product.html",context)

# edita productos ya existentes
def edit_products(request, element_id):
    element = get_object_or_404(Element, id=element_id)

    if request.method == "POST":
        if request.POST.get("action") == "delete":
            element.delete()
            return redirect("inventory")

        form = CreateElementForm(request.POST, instance=element)

        if form.is_valid():
            category_name = form.cleaned_data.pop("category").strip()
            type_name = form.cleaned_data.pop("type").strip()

            category, _ = Category.objects.get_or_create(name=category_name, defaults={"slug": slugify(category_name)})
            type_obj, _ = Type.objects.get_or_create(
                name=type_name,
                category=category,
                defaults={"slug": f"{category.slug}-{slugify(type_name)}"},
            )

            element = form.save(commit=False)
            element.category = category
            element.type = type_obj

            base_slug = slugify(element.name) or f"elemento-{element.pk}"
            element_slug = base_slug
            suffix = 2
            while Element.objects.exclude(pk=element.pk).filter(slug=element_slug).exists():
                element_slug = f"{base_slug}-{suffix}"
                suffix += 1

            element.slug = element_slug
            element.save()

            return redirect("inventory")

        categories = Category.objects.all()
    else:
        form = CreateElementForm(
            instance=element,
            initial={
                "category": element.category.name,
                "type": element.type.name,
            },
        )
        categories = Category.objects.all()

    return render(
        request,
        "core/edit_products.html",
        {
            "form": form,
            "product": element,
            "categories": categories,
        },
    )

# funcionalidad corazón: lista priorizada
def prioritized_list(request):
    settings = InventorySettings.objects.filter(pk=1).first()
    settings_form = InventorySettingsForm(instance=settings)

    if request.method == "POST":
        settings_form = InventorySettingsForm(request.POST, instance=settings)
        if settings_form.is_valid():
            settings = settings_form.save(commit=False)
            settings.pk = 1
            settings.save()
            messages.success(request, "Se guardaron los días entre reposiciones.")
            return redirect("prioritized_list")

    elements = get_prioritized_elements(
        settings.replenishment_days if settings else None
    )

    return render(
        request,
        "core/prioritized_list.html",
        {
            "elements": elements,
            "replenishment_settings": settings,
            "settings_form": settings_form,
        },
    )

# funcionalidad 2: registro de ventas
def sales(request):
    registered_sales = Sale.objects.select_related("element").order_by("-date", "-id")
    sales_quantity = registered_sales.aggregate(total_quantity=models.Sum("quantity"))["total_quantity"] or 0
    monthly_sales = registered_sales.annotate(month=models.functions.TruncMonth("date")).values("month").annotate(total_quantity=models.Sum("quantity")).order_by("month")
    return render(
        request,
        "core/sales.html",
        {
            "sales": registered_sales,
            "sales_quantity": sales_quantity,
            "monthly_sales": monthly_sales,
            "product_search_enabled": True,
            **product_search_context(request),
        },
    )

def register_sales(request):
    form = SalesForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            Sale.objects.create(
                date=form.cleaned_data["date"],
                element=form.cleaned_data["associated_product"],
                quantity=form.cleaned_data["quantity_sold"],
            )
            if quantity := form.cleaned_data["quantity_sold"]:
                associated_product = form.cleaned_data["associated_product"]
                associated_product.quantity -= quantity
                associated_product.save()
            return redirect("sales")

    return render(request, "core/register_sales.html", {"form": form})

def frequency_analysis(request):
    
    sales_data = (
        Sale.objects.values("element__name")
        .annotate(total_quantity=models.Sum("quantity"))
        .order_by("-total_quantity")
    )
    return render(request, "core/frequency_analysis.html", {"sales_data": sales_data})