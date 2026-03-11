from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChannelConfigViewSet

router = DefaultRouter()
router.register('', ChannelConfigViewSet, basename='channels')

urlpatterns = [path('', include(router.urls))]
