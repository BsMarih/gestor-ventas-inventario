from django.db import models
from django.shortcuts import get_object_or_404, render,redirect
from django.views.generic import ListView
from django.core.paginator import Paginator
from .forms import CreateElementForm, SalesForm
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.text import slugify
from django.http import JsonResponse

from .models import Element,Type,Category,Sale

# Create your views here.
def index(request):
    prioritized_products = (Element.objects.filter(quantity__lte=models.F("min_quantity"))
        .order_by("quantity", "id")[:5])
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
        },
    )

# vista que muestra detalles de productos
def detail(request,pk):
    element = get_object_or_404(Element, pk=pk)
    return render(request, "core/detail.html", {"element": element})

def get_types(request):
    category_name = request.GET.get('category')
    try:
        category = Category.objects.get(name=category_name)
        types = list(Type.objects.filter(category=category).values_list('name', flat=True))
    except Category.DoesNotExist:
        types = []

    return JsonResponse(types, safe=False)


def inventory(request):
    elements = Element.objects.all().order_by('-id')

    paginator = Paginator(elements, 10)
    page_number = request.GET.get('page')
    elements_page = paginator.get_page(page_number)

    return render(request, "core/inventory.html", {"elements": elements_page})

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
        form = CreateElementForm()

    context = {"form": form,"categories": Category.objects.all(),"types": Type.objects.all(),}

    return render(request,"core/create_product.html",context)

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
    elements = Element.objects.filter(quantity__lte=models.F('min_quantity')).order_by('quantity')
    

    return render(request, "core/prioritized_list.html", {"elements": elements})

def sales(request):
    registered_sales = Sale.objects.select_related("element").order_by("-date", "-id")
    sales_quantity = registered_sales.aggregate(total_quantity=models.Sum("quantity"))["total_quantity"] or 0
    monthly_sales = registered_sales.annotate(month=models.functions.TruncMonth("date")).values("month").annotate(total_quantity=models.Sum("quantity")).order_by("month")
    return render(request, "core/sales.html", {"sales": registered_sales, "sales_quantity": sales_quantity, "monthly_sales": monthly_sales})

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