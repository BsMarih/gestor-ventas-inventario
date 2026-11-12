from django.urls import path
from django.core.paginator import Paginator
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('search/', views.product_search, name='product_search'),
    path('sales/', views.sales, name='sales'),
    path('inventory/', views.inventory, name='inventory'),
    path('inventory/scan/', views.product_scan, name='product_scan'),
    path('detail/<int:pk>/', views.detail, name='detail'),
    path("create/", views.create_element, name="create_element"),
    path('ajax/get_types/', views.get_types, name='get_types'),
    path('edit/<int:element_id>/', views.edit_products, name='edit_product'),
    path('prioritized_list/', views.prioritized_list, name='prioritized_list'),
    path("register_sales/", views.register_sales, name="register_sales"),
]