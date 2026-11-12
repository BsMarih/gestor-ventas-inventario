from django.db import models
from django.core.exceptions import ValidationError

# Create your models here.
class Category(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    def __str__(self):
        return self.name

class Type(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    category = models.ForeignKey(Category,on_delete=models.CASCADE,null=False,blank=False)

    def __str__(self):
        return self.name


def mayor_a_cero(value):
    if value <= 0:
        raise ValidationError("El valor debe ser mayor a cero.")

class Element(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    description = models.TextField(blank=True)
    barcode = models.CharField(max_length=50, blank=True, default="", db_index=True)
    price = models.PositiveIntegerField(validators=[mayor_a_cero])
    quantity= models.PositiveIntegerField(default=0)
    min_quantity= models.PositiveIntegerField(validators=[mayor_a_cero])
    associated_min_percentage = models.DecimalField(max_digits=5, decimal_places=2, validators=[mayor_a_cero])

    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    type= models.ForeignKey(Type, on_delete=models.CASCADE)
    prod_website = models.URLField(max_length=255, default='', blank=True, null=True)
    created= models.DateTimeField(auto_now_add=True)
    updated= models.DateTimeField(auto_now=True)

    @property
    def state(self):
        if self.quantity == 0:
            return "Agotado"
        if self.quantity < self.min_quantity:
            return "Disponible - Stock bajo"
        if (
            self.associated_min_percentage > 0 and self.quantity > (100 * self.min_quantity) / self.associated_min_percentage
        ):
            return "Disponible - Stock alto"
        return "Disponible"

    def __str__(self):
        return self.name

class Sale(models.Model):
    date = models.DateField()
    element = models.ForeignKey(Element, on_delete=models.CASCADE, related_name="sales")
    quantity = models.PositiveIntegerField()
    repositiondays = models.PositiveIntegerField(
        validators=[mayor_a_cero],
        blank=True,
        null=True,
    )

    def __str__(self):
        return f"Venta #{self.pk}"


class InventorySettings(models.Model):
    replenishment_days = models.PositiveIntegerField(validators=[mayor_a_cero])

    def __str__(self):
        return f"Reposición cada {self.replenishment_days} días"
