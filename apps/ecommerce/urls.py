from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProductViewSet,
    OrderViewSet,
    InventoryMovementViewSet,
    PromotionViewSet,  # P1.1
    ProductRelationViewSet,  # P1.1
)

router = DefaultRouter()
router.register('products', ProductViewSet, basename='products')
router.register('orders', OrderViewSet, basename='orders')
router.register('inventory', InventoryMovementViewSet, basename='inventory')
router.register('promotions', PromotionViewSet, basename='promotions')  # P1.1
router.register('product-relations', ProductRelationViewSet, basename='product_relations')  # P1.1

urlpatterns = [path('', include(router.urls))]
