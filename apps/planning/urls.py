from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.planning.views import ProjectPlanViewSet, FeatureViewSet, TaskViewSet

router = DefaultRouter()
router.register(r'plans', ProjectPlanViewSet, basename='project-plan')
router.register(r'features', FeatureViewSet, basename='feature')
router.register(r'tasks', TaskViewSet, basename='task')

urlpatterns = [
    path('', include(router.urls)),
]
