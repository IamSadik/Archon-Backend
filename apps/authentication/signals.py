# Signals file - UserProfile signals removed since table was deleted
# Keep this file for future signal needs

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User


# UserProfile signals removed - table no longer exists
# Add any future user-related signals here
