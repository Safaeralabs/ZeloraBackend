from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FlowViewSet, flow_intents_list, flow_intent_delete

router = DefaultRouter()
router.register('', FlowViewSet, basename='flows')

urlpatterns = [
    path('intents/', flow_intents_list, name='flow-intents'),
    path('intents/<uuid:intent_id>/', flow_intent_delete, name='flow-intent-delete'),
    path('', include(router.urls)),
]
