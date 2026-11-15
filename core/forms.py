from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils.html import format_html
from .models import Element, InventorySettings

class CreateElementForm(forms.ModelForm):

    category = forms.CharField(max_length=255, strip=True)
    type = forms.CharField(max_length=255, strip=True)

    class Meta:
        model = Element
        labels = {
            'name': 'Nombre de artículo',
            'description': 'Descripción',
            'barcode': 'Código de barras',
            'price': 'Precio',
            'quantity': 'Cantidad',
            'min_quantity': 'Cantidad mínima',
            'associated_min_percentage': 'Porcentaje asociado a la cantidad mínima',
            'prod_website': 'Link del producto',
        }
        fields = [
            'name',
            'description',
            'barcode',
            'price',
            'quantity',
            'min_quantity',
            'associated_min_percentage',
            'prod_website',
        ]

class SalesForm(forms.Form):
    date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Fecha de venta",
    )
    barcode = forms.CharField(
        required=False,
        max_length=50,
        label="Código de barras",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "autofocus": True,
                "placeholder": "Escanea o escribe el código",
            }
        ),
    )
    associated_product = forms.ModelChoiceField(
        queryset=Element.objects.all(),
        required=False,
        label="Producto asociado",
    )
    quantity_sold = forms.IntegerField(min_value=1, label="Cantidad vendida")

    def clean(self):
        cleaned_data = super().clean()
        barcode = cleaned_data.get("barcode", "").strip()
        product = cleaned_data.get("associated_product")
        quantity = cleaned_data.get("quantity_sold")

        if barcode:
            matching_products = list(
                Element.objects.filter(barcode=barcode).order_by("pk")[:2]
            )
            if not matching_products:
                self.add_error(
                    "barcode",
                    "No hay un producto registrado en el inventario con ese código.",
                )
            elif len(matching_products) > 1:
                self.add_error(
                    "barcode",
                    "El código corresponde a más de un producto. Corrige el código en el inventario.",
                )
            else:
                barcode_product = matching_products[0]
                if product and product.pk != barcode_product.pk:
                    self.add_error(
                        "associated_product",
                        "El código de barras no coincide con el producto seleccionado.",
                    )
                else:
                    product = barcode_product
                    cleaned_data["associated_product"] = product
        elif not product:
            self.add_error(
                "associated_product",
                "Selecciona un producto o ingresa su código de barras.",
            )

        if product and quantity and quantity > product.quantity:
            self.add_error(
                "quantity_sold",
                "La cantidad vendida no puede superar el stock disponible.",
            )
        return cleaned_data


class InventorySettingsForm(forms.ModelForm):
    class Meta:
        model = InventorySettings
        fields = ["replenishment_days"]
        labels = {"replenishment_days": "Días entre reposiciones"}
        widgets = {
            "replenishment_days": forms.NumberInput(
                attrs={"class": "form-control", "min": 1}
            )
        }
        help_texts = {
            "replenishment_days": (
                "La lista priorizará productos cuyo stock estimado no alcance "
                "hasta la próxima reposición."
            )
        }


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "El usuario o la contraseña no son correctos.",
        "inactive": "Esta cuenta está inactiva.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Nombre de usuario"
        self.fields["username"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "username"}
        )
        self.fields["password"].label = "Contraseña"
        self.fields["password"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "current-password"}
        )


class CreateAccountForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label="Correo electrónico",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Nombre de usuario"
        self.fields["username"].help_text = (
            "Obligatorio. Máximo 150 caracteres. Solo se permiten letras, "
            "números y @/./+/-/_."
        )
        self.fields["username"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "username"}
        )
        self.fields["email"].widget.attrs["class"] = "form-control"
        self.fields["password1"].label = "Contraseña"
        self.fields["password1"].help_text = format_html(
            "<ul><li>{}</li><li>{}</li><li>{}</li><li>{}</li></ul>",
            "La contraseña no puede ser demasiado similar a tu otra información personal.",
            "Debe contener al menos 8 caracteres.",
            "No puede ser una contraseña de uso común.",
            "No puede estar formada únicamente por números.",
        )
        self.fields["password1"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "new-password"}
        )
        self.fields["password2"].label = "Confirmar contraseña"
        self.fields["password2"].help_text = (
            "Introduce la misma contraseña que antes para verificarla."
        )
        self.fields["password2"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "new-password"}
        )


class UserForm(forms.Form):
    username = forms.CharField(label="Nombre de usuario", max_length=150)
    email = forms.EmailField(label="Correo electrónico")
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)