from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from apps.projects.models import Project
from apps.context.tasks import index_project_files

@receiver(post_save, sender=Project)
def trigger_project_indexing(sender, instance, created, **kwargs):
    """
    Trigger automatic file indexing when a new project is created
    and has a repository path.
    """
    if created and instance.repository_path:
        # Use on_commit to ensure transaction is complete before task runs
        transaction.on_commit(lambda: index_project_files.delay(instance.id))
