from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FlowViewSet

router = DefaultRouter()
router.register('', FlowViewSet, basename='flows')

urlpatterns = [path('', include(router.urls))]
