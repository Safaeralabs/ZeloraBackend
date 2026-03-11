from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CollabNoteViewSet, AgentPerformanceViewSet

router = DefaultRouter()
router.register('notes', CollabNoteViewSet, basename='collab-notes')
router.register('agent-performance', AgentPerformanceViewSet, basename='agent-performance')

urlpatterns = [path('', include(router.urls))]
