from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, OrderViewSet, InventoryMovementViewSet

router = DefaultRouter()
router.register('products', ProductViewSet, basename='products')
router.register('orders', OrderViewSet, basename='orders')
router.register('inventory', InventoryMovementViewSet, basename='inventory')

urlpatterns = [path('', include(router.urls))]
