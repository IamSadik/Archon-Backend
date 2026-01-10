from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.authentication.urls')),
    path('api/projects/', include('apps.projects.urls')),
    path('api/context/', include('apps.context.urls')),
    path('api/memory/', include('apps.memory.urls')),
    path('api/planning/', include('apps.planning.urls')),
    path('api/agents/', include('apps.agents.urls')),
    path('api/chat/', include('apps.chat.urls')),
    path('api/vector-store/', include('apps.vector_store.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
