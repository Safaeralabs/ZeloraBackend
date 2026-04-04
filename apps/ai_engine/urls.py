from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CopilotView,
    SummarizeView,
    IntentDetectView,
    QAScoreView,
    AITaskViewSet,
    AIInsightViewSet,
    AIPerformanceViewSet,
)


router = DefaultRouter()
router.register('tasks', AITaskViewSet, basename='ai-tasks')
router.register('insights', AIInsightViewSet, basename='ai-insights')
router.register('performance', AIPerformanceViewSet, basename='ai-performance')

urlpatterns = [
    path('copilot/', CopilotView.as_view(), name='ai-copilot'),
    path('summarize/', SummarizeView.as_view(), name='ai-summarize'),
    path('intent/', IntentDetectView.as_view(), name='ai-intent'),
    path('qa-score/', QAScoreView.as_view(), name='ai-qa-score'),
path('', include(router.urls)),
]
