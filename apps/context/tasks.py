import logging
from celery import shared_task
from django.conf import settings
from apps.projects.models import Project
from apps.context.services.file_indexer import FileIndexerService

logger = logging.getLogger(__name__)

@shared_task
def index_project_files(project_id):
    """
    Celery task to automatically index project files.
    """
    try:
        project = Project.objects.get(id=project_id)
        if not project.repository_path:
            logger.info(f"No repository path for project {project_id}, skipping indexing.")
            return
            
        logger.info(f"Starting automatic indexing for project {project.name} ({project_id})")
        
        indexer = FileIndexerService(project=project)
        result = indexer.index_directory(
            directory_path=project.repository_path,
            recursive=True,
            analyze_code=True,
            create_embeddings=True,
            max_files=500  # Reasonable limit for auto-scan
        )
        
        logger.info(f"Completed indexing for project {project_id}: {result}")
        return result
        
    except Project.DoesNotExist:
        logger.error(f"Project {project_id} not found for indexing")
    except Exception as e:
        logger.error(f"Error indexing project {project_id}: {str(e)}")
