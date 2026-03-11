from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import KBArticleViewSet, KBDocumentViewSet

router = DefaultRouter()
router.register('articles', KBArticleViewSet, basename='kb-articles')
router.register('documents', KBDocumentViewSet, basename='kb-documents')

urlpatterns = [path('', include(router.urls))]
