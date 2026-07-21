from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CopilotView,
    TonePreviewView,
    SummarizeView,
    IntentDetectView,
    QAScoreView,
    AITaskViewSet,
    AIInsightViewSet,
    AIPerformanceViewSet,
    SalesSessionMetricsView,
    VoiceImportPreviewView,
    VoiceImportApplyView,
)


router = DefaultRouter()
router.register('tasks', AITaskViewSet, basename='ai-tasks')
router.register('insights', AIInsightViewSet, basename='ai-insights')
router.register('performance', AIPerformanceViewSet, basename='ai-performance')

urlpatterns = [
    path('copilot/', CopilotView.as_view(), name='ai-copilot'),
    path('tone-preview/', TonePreviewView.as_view(), name='ai-tone-preview'),
    path('summarize/', SummarizeView.as_view(), name='ai-summarize'),
    path('intent/', IntentDetectView.as_view(), name='ai-intent'),
    path('qa-score/', QAScoreView.as_view(), name='ai-qa-score'),
    path('sales-sessions/metrics/', SalesSessionMetricsView.as_view(), name='ai-sales-session-metrics'),
    path('voice-import/preview/', VoiceImportPreviewView.as_view(), name='ai-voice-import-preview'),
    path('voice-import/apply/', VoiceImportApplyView.as_view(), name='ai-voice-import-apply'),
    path('', include(router.urls)),
]
