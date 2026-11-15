from django.urls import path
from django.core.paginator import Paginator
from django.contrib.auth import views as auth_views
from .forms import LoginForm
from . import views

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="core/login.html",
            authentication_form=LoginForm,
            redirect_authenticated_user=True,
            next_page="index",
        ),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(next_page="login"),
        name="logout",
    ),
    path("register/", views.register_account, name="register_account"),
    path(
        "notifications/dismiss/",
        views.dismiss_notification,
        name="dismiss_notification",
    ),
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