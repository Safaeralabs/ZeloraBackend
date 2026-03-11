from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TemplateViewSet, CampaignViewSet

router = DefaultRouter()
router.register('templates', TemplateViewSet, basename='templates')
router.register('campaigns', CampaignViewSet, basename='campaigns')

urlpatterns = [path('', include(router.urls))]
