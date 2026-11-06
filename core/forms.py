from django import forms
from .models import Element

class CreateElementForm(forms.ModelForm):

    category = forms.CharField(max_length=255, strip=True)
    type = forms.CharField(max_length=255, strip=True)

    class Meta:
        model = Element
        fields = [
            'name',
            'description',
            'price',
            'quantity',
            'min_quantity',
            'associated_min_percentage',
            'prod_website',
        ]

class SalesForm(forms.Form):
    date=forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label="Fecha de venta")
    associated_product=forms.ModelChoiceField(queryset=Element.objects.all(), label="Producto asociado")
    quantity_sold=forms.IntegerField(min_value=1, label="Cantidad vendida")

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get("associated_product")
        quantity = cleaned_data.get("quantity_sold")
        if product and quantity and quantity > product.quantity:
            self.add_error(
                "quantity_sold",
                "La cantidad vendida no puede superar el stock disponible.",
            )
        return cleaned_data

class UserForm(forms.Form):
    username = forms.CharField(label="Nombre de usuario", max_length=150)
    email = forms.EmailField(label="Correo electrónico")
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)