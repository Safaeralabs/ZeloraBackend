from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OverviewView,
    SummaryView,
    HourlyView,
    ChannelMetricsView,
    IntentMetricsView,
    MetricsSnapshotViewSet,
)

router = DefaultRouter()
router.register('snapshots', MetricsSnapshotViewSet, basename='metrics-snapshots')

urlpatterns = [
    path('overview/', OverviewView.as_view(), name='analytics-overview'),
    path('summary/', SummaryView.as_view(), name='analytics-summary'),
    path('hourly/', HourlyView.as_view(), name='analytics-hourly'),
    path('channels/', ChannelMetricsView.as_view(), name='analytics-channels'),
    path('intents/', IntentMetricsView.as_view(), name='analytics-intents'),
    path('', include(router.urls)),
]
