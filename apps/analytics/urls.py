from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OverviewView,
    SummaryView,
    HourlyView,
    ChannelMetricsView,
    IntentMetricsView,
    SalesAgentMetricsView,
    MetricsSnapshotViewSet,
    HistoricalImportView,
    HistoricalImportKBView,
    LearningCandidateView,
    LearningCandidateApproveView,
    LearningCandidateRejectView,
    LearningCandidateBatchView,
    DocumentExtractionCandidateView,
    DocumentExtractionCandidateApproveView,
    DocumentExtractionCandidateRejectView,
    DocumentExtractionCandidateBatchView,
)

router = DefaultRouter()
router.register('snapshots', MetricsSnapshotViewSet, basename='metrics-snapshots')

urlpatterns = [
    path('overview/', OverviewView.as_view(), name='analytics-overview'),
    path('summary/', SummaryView.as_view(), name='analytics-summary'),
    path('hourly/', HourlyView.as_view(), name='analytics-hourly'),
    path('channels/', ChannelMetricsView.as_view(), name='analytics-channels'),
    path('intents/', IntentMetricsView.as_view(), name='analytics-intents'),
    path('sales-agent/', SalesAgentMetricsView.as_view(), name='analytics-sales-agent'),
    path('historical-imports/', HistoricalImportView.as_view(), name='analytics-historical-imports'),
    path('historical-imports/import-kb/', HistoricalImportKBView.as_view(), name='analytics-historical-imports-kb'),
    path('learning-candidates/', LearningCandidateView.as_view(), name='analytics-learning-candidates'),
    path('learning-candidates/batch/', LearningCandidateBatchView.as_view(), name='analytics-learning-candidates-batch'),
    path('learning-candidates/<uuid:pk>/approve/', LearningCandidateApproveView.as_view(), name='analytics-learning-candidates-approve'),
    path('learning-candidates/<uuid:pk>/reject/', LearningCandidateRejectView.as_view(), name='analytics-learning-candidates-reject'),
    path('document-extraction-candidates/', DocumentExtractionCandidateView.as_view(), name='analytics-document-extraction-candidates'),
    path('document-extraction-candidates/batch/', DocumentExtractionCandidateBatchView.as_view(), name='analytics-document-extraction-candidates-batch'),
    path('document-extraction-candidates/<uuid:pk>/approve/', DocumentExtractionCandidateApproveView.as_view(), name='analytics-document-extraction-candidates-approve'),
    path('document-extraction-candidates/<uuid:pk>/reject/', DocumentExtractionCandidateRejectView.as_view(), name='analytics-document-extraction-candidates-reject'),
    path('', include(router.urls)),
]
