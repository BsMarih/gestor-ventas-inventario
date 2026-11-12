from io import BytesIO
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from .models import Category, Element, InventorySettings, Sale, Type
from .views import lookup_product_catalogs


class CreateElementTypeTests(TestCase):
    def create_element(self, name, category, type_name):
        return self.client.post(
            reverse("create_element"),
            {
                "name": name,
                "category": category,
                "type": type_name,
                "price": "10",
                "quantity": "5",
                "min_quantity": "1",
                "associated_min_percentage": "50",
            },
        )

    def test_new_type_is_created_for_selected_category(self):
        response = self.create_element("Bife", "Comida", "Carne")

        self.assertRedirects(response, reverse("inventory"))
        element = Element.objects.get(name="Bife")
        self.assertEqual(element.category.name, "Comida")
        self.assertEqual(element.type.name, "Carne")
        self.assertEqual(element.type.category, element.category)

    def test_type_names_can_be_reused_in_different_categories(self):
        self.create_element("Bife", "Comida", "Carne")
        self.create_element("Alimento para perro", "Mascotas", "Carne")

        food_type = Type.objects.get(category__name="Comida", name="Carne")
        pet_type = Type.objects.get(category__name="Mascotas", name="Carne")
        self.assertNotEqual(food_type.pk, pet_type.pk)
        self.assertNotEqual(food_type.slug, pet_type.slug)

    def test_get_types_returns_only_types_for_requested_category(self):
        food = Category.objects.create(name="Comida", slug="comida")
        pets = Category.objects.create(name="Mascotas", slug="mascotas")
        Type.objects.create(name="Carne", slug="comida-carne", category=food)
        Type.objects.create(name="Carne", slug="mascotas-carne", category=pets)

        response = self.client.get(reverse("get_types"), {"category": "Comida"})

        self.assertEqual(response.json(), ["Carne"])


class ProductScanTests(TestCase):
    @patch(
        "core.views.urlopen",
        return_value=BytesIO(
            b'{"status":1,"product":{"product_name":"Jugo",'
            b'"generic_name":"Jugo natural","brands":"Ejemplo",'
            b'"quantity":"1 l","categories_hierarchy":["en:beverages","en:juices"]}}'
        ),
    )
    def test_open_food_facts_product_is_mapped_to_creation_fields(self, urlopen_mock):
        product, error = lookup_product_catalogs("12345678")

        self.assertIsNone(error)
        self.assertEqual(product["name"], "Jugo")
        self.assertEqual(product["description"], "Jugo natural | Marca: Ejemplo | Presentación: 1 l")
        self.assertEqual(product["category"], "Alimentos")
        self.assertEqual(product["type"], "juices")
        urlopen_mock.assert_called_once()

    @patch("core.views.urlopen")
    def test_invalid_barcode_does_not_query_public_api(self, urlopen_mock):
        product, error = lookup_product_catalogs("not-a-barcode")

        self.assertIsNone(product)
        self.assertIn("8 y 14 dígitos", error)
        urlopen_mock.assert_not_called()

    @patch(
        "core.views.urlopen",
        side_effect=[
            BytesIO(b'{"status":0}'),
            BytesIO(
                b'{"status":1,"product":{"product_name":"Crema",'
                b'"brands":"Ejemplo","categories_hierarchy":["en:skin-care"]}}'
            ),
        ],
    )
    def test_search_falls_back_to_beauty_facts(self, urlopen_mock):
        product, error = lookup_product_catalogs("12345678")

        self.assertIsNone(error)
        self.assertEqual(product["name"], "Crema")
        self.assertEqual(product["category"], "Higiene y belleza")
        self.assertEqual(product["type"], "skin care")
        self.assertIn("world.openfoodfacts.org", urlopen_mock.call_args_list[0].args[0].full_url)
        self.assertIn("world.openbeautyfacts.org", urlopen_mock.call_args_list[1].args[0].full_url)
        self.assertEqual(urlopen_mock.call_count, 2)

    @patch(
        "core.views.urlopen",
        side_effect=[
            BytesIO(b'{"status":0}'),
            BytesIO(b'{"status":0}'),
            BytesIO(
                b'{"status":1,"product":{"product_name":"L\xc3\xa1mpara",'
                b'"categories_hierarchy":["en:home","en:lighting"]}}'
            ),
        ],
    )
    def test_search_falls_back_to_open_products_facts(self, urlopen_mock):
        product, error = lookup_product_catalogs("12345678")

        self.assertIsNone(error)
        self.assertEqual(product["name"], "Lámpara")
        self.assertEqual(product["category"], "Productos generales")
        self.assertEqual(product["type"], "lighting")
        self.assertEqual(urlopen_mock.call_count, 3)

    def test_inventory_has_separate_scan_button(self):
        response = self.client.get(reverse("inventory"))

        self.assertContains(response, reverse("product_scan"))
        self.assertContains(response, "Escanear código de barras")

    def test_scan_page_renders_camera_reader(self):
        response = self.client.get(reverse("product_scan"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Html5QrcodeScanner")
        self.assertContains(response, "html5-qrcode@2.3.8")

    @patch(
        "core.views.lookup_product_catalogs",
        return_value=(
            {
                "name": "Jugo de naranja",
                "description": "Marca: Ejemplo | Presentación: 1 l",
                "category": "Alimentos",
                "type": "Jugos",
            },
            None,
        ),
    )
    def test_scanned_product_prefills_editable_creation_form(self, lookup):
        response = self.client.get(
            reverse("create_element"),
            {"barcode": "12345678"},
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form["name"].value(), "Jugo de naranja")
        self.assertEqual(form["description"].value(), "Marca: Ejemplo | Presentación: 1 l")
        self.assertEqual(form["barcode"].value(), "12345678")
        self.assertContains(response, "Revisa o completa los datos antes de guardar")
        lookup.assert_called_once_with("12345678")

    def test_scanned_barcode_is_saved_with_product(self):
        response = self.client.post(
            reverse("create_element"),
            {
                "name": "Jugo",
                "barcode": "12345678",
                "category": "Bebidas",
                "type": "Jugos",
                "price": "25",
                "quantity": "8",
                "min_quantity": "2",
                "associated_min_percentage": "50",
            },
        )

        self.assertRedirects(response, reverse("inventory"))
        self.assertEqual(Element.objects.get(name="Jugo").barcode, "12345678")


class InventoryPaginationTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Comida", slug="comida")
        product_type = Type.objects.create(
            name="Carne",
            slug="comida-carne",
            category=category,
        )
        Element.objects.bulk_create(
            [
                Element(
                    name=f"Producto {number}",
                    slug=f"producto-{number}",
                    price=10,
                    min_quantity=1,
                    associated_min_percentage=50,
                    category=category,
                    type=product_type,
                )
                for number in range(11)
            ]
        )

    def test_inventory_shows_ten_products_per_page(self):
        response = self.client.get(reverse("inventory"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["elements"]), 10)
        self.assertEqual(response.context["elements"].paginator.num_pages, 2)

    def test_inventory_next_page_shows_remaining_products(self):
        response = self.client.get(reverse("inventory"), {"page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["elements"]), 1)
        self.assertEqual(response.context["elements"].number, 2)
        self.assertContains(response, "Anterior")
        self.assertContains(response, "Siguiente")

    def test_invalid_page_number_falls_back_to_first_page(self):
        response = self.client.get(reverse("inventory"), {"page": "no-es-un-numero"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["elements"].number, 1)

    def test_zero_stock_product_is_shown_with_zero_stock(self):
        response = self.client.get(reverse("inventory"))

        self.assertContains(response, "Stock: 0")


class ProductStateTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Comida", slug="comida")
        product_type = Type.objects.create(
            name="Carne",
            slug="comida-carne",
            category=category,
        )
        self.product = Element.objects.create(
            name="Bife",
            slug="bife",
            price=10,
            quantity=3,
            min_quantity=3,
            associated_min_percentage=50,
            category=category,
            type=product_type,
        )

    def test_state_reflects_stock_thresholds(self):
        cases = [
            (0, "Agotado"),
            (2, "Disponible: Stock bajo"),
            (3, "Disponible"),
            (6, "Disponible"),
            (7, "Disponible: Stock alto"),
        ]

        for quantity, expected_state in cases:
            with self.subTest(quantity=quantity):
                self.product.quantity = quantity
                self.assertEqual(self.product.state, expected_state)

    def test_zero_percentage_does_not_raise_division_error(self):
        self.product.associated_min_percentage = 0
        self.assertEqual(self.product.state, "Disponible")

    def test_inventory_renders_calculated_product_state(self):
        response = self.client.get(reverse("inventory"))

        self.assertContains(response, "Estado: Disponible")


class EditElementTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Comida", slug="comida")
        self.product_type = Type.objects.create(
            name="Carne",
            slug="comida-carne",
            category=self.category,
        )
        self.element = Element.objects.create(
            name="Bife",
            slug="bife",
            price=10,
            min_quantity=1,
            associated_min_percentage=50,
            category=self.category,
            type=self.product_type,
        )

    def test_edit_page_loads_existing_product_and_type_values(self):
        response = self.client.get(
            reverse("edit_product", args=[self.element.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"]["category"].value(), "Comida")
        self.assertEqual(response.context["form"]["type"].value(), "Carne")

    def test_post_updates_product_and_category_type_relationship(self):
        response = self.client.post(
            reverse("edit_product", args=[self.element.pk]),
            {
                "name": "Jugo",
                "description": "Jugo natural",
                "price": "25",
                "quantity": "8",
                "min_quantity": "2",
                "associated_min_percentage": "50",
                "category": "Bebidas",
                "type": "Jugo natural",
                "prod_website": "",
            },
        )

        self.assertRedirects(response, reverse("inventory"))
        self.element.refresh_from_db()
        self.assertEqual(self.element.name, "Jugo")
        self.assertEqual(self.element.category.name, "Bebidas")
        self.assertEqual(self.element.type.name, "Jugo natural")
        self.assertEqual(self.element.type.category, self.element.category)
        self.assertEqual(self.element.price, 25)
        self.assertEqual(self.element.quantity, 8)

    def test_invalid_edit_keeps_product_and_renders_errors(self):
        response = self.client.post(
            reverse("edit_product", args=[self.element.pk]),
            {
                "name": "Bife",
                "price": "-1",
                "quantity": "5",
                "min_quantity": "1",
                "category": "Comida",
                "type": "Carne",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.element.refresh_from_db()
        self.assertEqual(self.element.price, 10)

    def test_delete_action_removes_product_and_redirects_to_inventory(self):
        response = self.client.post(
            reverse("edit_product", args=[self.element.pk]),
            {"action": "delete"},
        )

        self.assertRedirects(response, reverse("inventory"))
        self.assertFalse(Element.objects.filter(pk=self.element.pk).exists())


class PrioritizedProductPreviewTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Comida", slug="comida")
        product_type = Type.objects.create(
            name="Carne",
            slug="comida-carne",
            category=category,
        )
        Element.objects.bulk_create(
            [
                Element(
                    name=f"Prioridad {quantity}",
                    slug=f"prioridad-{quantity}",
                    quantity=quantity,
                    min_quantity=6,
                    category=category,
                    type=product_type,
                )
                for quantity in range(7)
            ]
            + [
                Element(
                    name="Stock suficiente",
                    slug="stock-suficiente",
                    quantity=8,
                    min_quantity=6,
                    category=category,
                    type=product_type,
                )
            ]
        )

    def test_index_shows_at_most_five_most_urgent_products(self):
        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        products = response.context["prioritized_products"]
        self.assertEqual(len(products), 5)
        self.assertEqual(
            [product.name for product in products],
            [f"Prioridad {quantity}" for quantity in range(5)],
        )
        self.assertNotContains(response, "Stock suficiente")

    def test_index_shows_empty_message_when_no_products_need_restocking(self):
        Element.objects.filter(quantity__lte=6).delete()

        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["prioritized_products"]), 0)
        self.assertContains(
            response,
            "No hay productos que cumplan con el criterio de cantidad mínima.",
        )


class PrioritizedListForecastTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Comida", slug="comida")
        product_type = Type.objects.create(
            name="Carne",
            slug="comida-carne",
            category=category,
        )
        self.fast_seller = Element.objects.create(
            name="Producto de venta frecuente",
            slug="venta-frecuente",
            price=10,
            quantity=20,
            min_quantity=2,
            associated_min_percentage=50,
            category=category,
            type=product_type,
        )
        self.sufficient_stock = Element.objects.create(
            name="Stock suficiente",
            slug="stock-suficiente-priorizado",
            price=10,
            quantity=100,
            min_quantity=2,
            associated_min_percentage=50,
            category=category,
            type=product_type,
        )

    def configure_replenishment_days(self, days):
        return self.client.post(
            reverse("prioritized_list"),
            {"replenishment_days": days},
        )

    def test_first_visit_prompts_for_replenishment_days(self):
        response = self.client.get(reverse("prioritized_list"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["replenishment_settings"])
        self.assertContains(response, "Configurar período de reposición")
        self.assertContains(response, "Días entre reposiciones")

    def test_replenishment_days_are_saved_and_can_be_changed(self):
        response = self.configure_replenishment_days(14)

        self.assertRedirects(response, reverse("prioritized_list"))
        settings = InventorySettings.objects.get(pk=1)
        self.assertEqual(settings.replenishment_days, 14)

        response = self.configure_replenishment_days(7)

        self.assertRedirects(response, reverse("prioritized_list"))
        settings.refresh_from_db()
        self.assertEqual(settings.replenishment_days, 7)

    def test_replenishment_days_must_be_greater_than_zero(self):
        response = self.configure_replenishment_days(0)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(InventorySettings.objects.exists())
        self.assertTrue(response.context["settings_form"].errors)

    def test_forecast_prioritizes_products_that_may_run_out_before_restock(self):
        InventorySettings.objects.create(pk=1, replenishment_days=6)
        today = timezone.localdate()
        Sale.objects.create(
            date=today - timezone.timedelta(days=10),
            element=self.fast_seller,
            quantity=20,
        )
        Sale.objects.create(
            date=today - timezone.timedelta(days=5),
            element=self.fast_seller,
            quantity=20,
        )
        Sale.objects.create(
            date=today + timezone.timedelta(days=1),
            element=self.sufficient_stock,
            quantity=100,
        )

        response = self.client.get(reverse("prioritized_list"))

        products = response.context["elements"]
        self.assertEqual([product.pk for product in products], [self.fast_seller.pk])
        self.assertTrue(products[0].predicted_stockout)
        self.assertAlmostEqual(products[0].average_daily_sales, 40 / 11)
        self.assertAlmostEqual(products[0].days_until_stockout, 5.5)
        self.assertContains(response, "Podría agotarse antes de la próxima reposición.")

    def test_dashboard_preview_uses_the_configured_forecast(self):
        InventorySettings.objects.create(pk=1, replenishment_days=6)
        today = timezone.localdate()
        Sale.objects.create(
            date=today - timezone.timedelta(days=10),
            element=self.fast_seller,
            quantity=20,
        )
        Sale.objects.create(
            date=today - timezone.timedelta(days=5),
            element=self.fast_seller,
            quantity=20,
        )

        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [product.pk for product in response.context["prioritized_products"]],
            [self.fast_seller.pk],
        )

    def test_products_without_sales_history_are_still_listed_when_below_minimum(self):
        self.fast_seller.quantity = 1
        self.fast_seller.save()

        response = self.client.get(reverse("prioritized_list"))

        self.assertEqual(
            [product.pk for product in response.context["elements"]],
            [self.fast_seller.pk],
        )
        self.assertContains(response, "Sin historial de ventas")


class ProductSearchAndDetailSalesTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Bebidas", slug="bebidas")
        product_type = Type.objects.create(
            name="Jugos",
            slug="bebidas-jugos",
            category=category,
        )
        self.product = Element.objects.create(
            name="Jugo de naranja",
            slug="jugo-de-naranja",
            barcode="12345678",
            description="Bebida natural",
            price=10,
            quantity=12,
            min_quantity=2,
            associated_min_percentage=50,
            category=category,
            type=product_type,
        )

    def test_product_search_finds_product_by_name_barcode_and_category(self):
        for query in ("naranja", "12345678", "Bebidas", "Jugos"):
            with self.subTest(query=query):
                response = self.client.get(reverse("product_search"), {"q": query})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    [product.pk for product in response.context["search_results"]],
                    [self.product.pk],
                )
                self.assertContains(response, "Jugo de naranja")
                self.assertContains(response, "Resultados de búsqueda")

    def test_product_search_shows_empty_state_for_no_matches(self):
        response = self.client.get(
            reverse("product_search"),
            {"q": "Producto inexistente"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["search_results"])
        self.assertContains(response, "No se encontraron productos")

    def test_inventory_and_sales_pages_show_search_above_their_titles(self):
        for page_name, title in (
            ("inventory", "Inventario"),
            ("sales", "Ventas"),
        ):
            with self.subTest(page=page_name):
                response = self.client.get(reverse(page_name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'name="q"')
                self.assertLess(
                    response.content.index(b'name="q"'),
                    response.content.index(f"<h1>{title}</h1>".encode()),
                )

    def test_search_forms_on_summary_inventory_and_sales_open_results_page(self):
        for page_name in ("index", "inventory", "sales"):
            with self.subTest(page=page_name):
                response = self.client.get(reverse(page_name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    f'action="{reverse("product_search")}"',
                )

    def test_summary_search_is_above_title_without_search_heading(self):
        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertLess(
            response.content.index(b'name="q"'),
            response.content.index(b"Panel de Control"),
        )
        self.assertNotContains(response, "Buscar productos</h2>")

    def test_search_results_page_keeps_search_bar_at_the_top(self):
        response = self.client.get(
            reverse("product_search"),
            {"q": "naranja"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jugo de naranja")
        self.assertLess(
            response.content.index(b'name="q"'),
            response.content.index("<h1>Resultados de búsqueda</h1>".encode()),
        )

    def test_detail_shows_ten_most_recent_sales_first(self):
        today = timezone.localdate()
        for days_ago in range(12):
            Sale.objects.create(
                date=today - timezone.timedelta(days=days_ago),
                element=self.product,
                quantity=days_ago + 1,
            )

        response = self.client.get(reverse("detail", args=[self.product.pk]))

        self.assertEqual(response.status_code, 200)
        recent_sales = response.context["recent_sales"]
        self.assertEqual(len(recent_sales), 10)
        self.assertEqual(recent_sales[0].date, today)
        self.assertEqual(recent_sales[0].quantity, 1)
        self.assertEqual(recent_sales[9].date, today - timezone.timedelta(days=9))
        self.assertContains(response, "Ventas más recientes")
        self.assertContains(response, "Cantidad vendida")

    def test_detail_shows_message_when_product_has_no_sales(self):
        response = self.client.get(reverse("detail", args=[self.product.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["recent_sales"])
        self.assertContains(response, "Aún no hay ventas registradas para este artículo.")


class DashboardSalesMetricsTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Comida", slug="comida")
        product_type = Type.objects.create(
            name="Carne",
            slug="comida-carne",
            category=category,
        )
        self.active_element = Element.objects.create(
            name="Bife",
            slug="bife",
            price=10,
            quantity=1,
            min_quantity=1,
            associated_min_percentage=50,
            category=category,
            type=product_type,
        )
        Element.objects.create(
            name="Producto inactivo",
            slug="producto-inactivo",
            price=10,
            quantity=0,
            min_quantity=1,
            associated_min_percentage=50,
            category=category,
            type=product_type,
        )

    def test_dashboard_shows_current_month_revenue_and_all_time_units(self):
        today = timezone.localdate()
        previous_month = today.replace(day=1) - timezone.timedelta(days=1)
        Sale.objects.create(date=today, element=self.active_element, quantity=3)
        Sale.objects.create(date=previous_month, element=self.active_element, quantity=5)

        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["monthly_sales"], 30)
        self.assertEqual(response.context["sales_quantity"], 8)
        self.assertEqual(response.context["total_productos"], 1)

    def test_dashboard_metrics_are_zero_when_there_are_no_sales_or_products(self):
        Element.objects.all().delete()

        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["monthly_sales"], 0)
        self.assertEqual(response.context["sales_quantity"], 0)
        self.assertEqual(response.context["total_productos"], 0)

    def test_dashboard_does_not_count_products_with_zero_stock(self):
        Element.objects.filter(pk=self.active_element.pk).update(quantity=0)

        response = self.client.get(reverse("index"))

        self.assertEqual(response.context["total_productos"], 0)


class SalesRegistrationTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Comida", slug="comida")
        product_type = Type.objects.create(
            name="Carne",
            slug="comida-carne",
            category=category,
        )
        self.element = Element.objects.create(
            name="Bife",
            slug="bife",
            barcode="12345678",
            price=10,
            quantity=5,
            min_quantity=1,
            associated_min_percentage=50,
            category=category,
            type=product_type,
        )

    def test_registration_page_renders_form(self):
        response = self.client.get(reverse("register_sales"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registrar venta")
        self.assertContains(response, "Código de barras")
        self.assertContains(response, "Escribir código")
        self.assertContains(response, "Escanear con cámara")
        self.assertContains(response, "sales-barcode-reader")
        self.assertContains(response, "html5-qrcode@2.3.8")
        self.assertContains(response, "Producto asociado")

    def test_registered_product_can_be_sold_by_barcode(self):
        response = self.client.post(
            reverse("register_sales"),
            {
                "date": "2026-11-01",
                "barcode": "12345678",
                "quantity_sold": 2,
            },
        )

        self.assertRedirects(response, reverse("sales"))
        sale = Sale.objects.get()
        self.assertEqual(sale.element, self.element)
        self.assertEqual(sale.quantity, 2)
        self.element.refresh_from_db()
        self.assertEqual(self.element.quantity, 3)

    def test_unregistered_barcode_does_not_create_sale(self):
        response = self.client.post(
            reverse("register_sales"),
            {
                "date": "2026-11-01",
                "barcode": "99999999",
                "quantity_sold": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("barcode", response.context["form"].errors)
        self.assertFalse(Sale.objects.exists())

    def test_ambiguous_barcode_does_not_create_sale(self):
        Element.objects.create(
            name="Bife duplicado",
            slug="bife-duplicado",
            barcode="12345678",
            price=10,
            quantity=5,
            min_quantity=1,
            associated_min_percentage=50,
            category=self.element.category,
            type=self.element.type,
        )

        response = self.client.post(
            reverse("register_sales"),
            {
                "date": "2026-11-01",
                "barcode": "12345678",
                "quantity_sold": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("barcode", response.context["form"].errors)
        self.assertFalse(Sale.objects.exists())

    def test_barcode_sale_cannot_exceed_stock(self):
        response = self.client.post(
            reverse("register_sales"),
            {
                "date": "2026-11-01",
                "barcode": "12345678",
                "quantity_sold": 6,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("quantity_sold", response.context["form"].errors)
        self.assertFalse(Sale.objects.exists())

    def test_conflicting_barcode_and_selected_product_are_rejected(self):
        another_product = Element.objects.create(
            name="Jugo",
            slug="jugo",
            barcode="87654321",
            price=5,
            quantity=5,
            min_quantity=1,
            associated_min_percentage=50,
            category=self.element.category,
            type=self.element.type,
        )

        response = self.client.post(
            reverse("register_sales"),
            {
                "date": "2026-11-01",
                "barcode": "12345678",
                "associated_product": another_product.pk,
                "quantity_sold": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("associated_product", response.context["form"].errors)
        self.assertFalse(Sale.objects.exists())

    def test_valid_sale_is_saved_and_redirects_to_sales(self):
        response = self.client.post(
            reverse("register_sales"),
            {
                "date": "2026-11-01",
                "associated_product": self.element.pk,
                "quantity_sold": 2,
            },
        )

        self.assertRedirects(response, reverse("sales"))
        sale = Sale.objects.get()
        self.assertEqual(sale.element, self.element)
        self.assertEqual(sale.quantity, 2)

    def test_selling_last_units_sets_stock_to_zero(self):
        self.client.post(
            reverse("register_sales"),
            {
                "date": "2026-11-01",
                "associated_product": self.element.pk,
                "quantity_sold": 5,
            },
        )

        self.element.refresh_from_db()
        self.assertEqual(self.element.quantity, 0)

    def test_sale_cannot_exceed_stock(self):
        response = self.client.post(
            reverse("register_sales"),
            {
                "date": "2026-11-01",
                "associated_product": self.element.pk,
                "quantity_sold": 6,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("quantity_sold", response.context["form"].errors)
        self.assertFalse(Sale.objects.exists())

    def test_sales_page_lists_registered_sales(self):
        Sale.objects.create(
            date="2026-11-01",
            element=self.element,
            quantity=2,
        )

        response = self.client.get(reverse("sales"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bife")
        self.assertContains(response, "2")

    def test_invalid_sale_does_not_create_record(self):
        response = self.client.post(
            reverse("register_sales"),
            {
                "date": "2026-11-01",
                "associated_product": self.element.pk,
                "quantity_sold": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Sale.objects.exists())


class NotificationsTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Comida", slug="comida")
        product_type = Type.objects.create(
            name="Carne",
            slug="comida-carne",
            category=category,
        )
        self.product = Element.objects.create(
            name="Bife",
            slug="bife",
            quantity=1,
            min_quantity=2,
            category=category,
            type=product_type,
        )

    def test_base_shows_low_stock_and_recent_sale_notifications(self):
        Sale.objects.create(
            date=timezone.localdate(),
            element=self.product,
            quantity=1,
        )

        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["notification_count"], 2)
        self.assertContains(response, "Stock bajo")
        self.assertContains(response, "Venta registrada")
        self.assertContains(response, "Bife")

    def test_base_shows_empty_state_when_there_are_no_notifications(self):
        self.product.quantity = 5
        self.product.min_quantity = 2
        self.product.save()

        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["notification_count"], 0)
        self.assertContains(response, "No tienes notificaciones.")
