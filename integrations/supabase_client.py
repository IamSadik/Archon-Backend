from supabase import create_client, Client
from django.conf import settings


def get_supabase_client() -> Client:
    """Get Supabase client instance."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def get_supabase_admin_client() -> Client:
    """Get Supabase admin client with service key."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
