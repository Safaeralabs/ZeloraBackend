from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ConversationViewSet

router = DefaultRouter()
router.register('', ConversationViewSet, basename='conversations')

urlpatterns = [path('', include(router.urls))]
