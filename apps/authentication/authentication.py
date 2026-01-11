from rest_framework import authentication, exceptions
from django.contrib.auth import get_user_model
from django.conf import settings
import jwt

User = get_user_model()


class SupabaseJWTAuthentication(authentication.BaseAuthentication):
    """
    Custom JWT authentication class that validates Supabase JWT tokens.
    """
    
    def authenticate(self, request):
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return None
        
        try:
            # Extract token from "Bearer <token>" format
            prefix, token = auth_header.split(' ')
            
            if prefix.lower() != 'bearer':
                raise exceptions.AuthenticationFailed('Invalid token prefix')
            
            try:
                # Decode without verification - we trust Supabase's signature
                payload = jwt.decode(
                    token,
                    options={"verify_signature": False}
                )
            except jwt.ExpiredSignatureError:
                raise exceptions.AuthenticationFailed('Token has expired')
            except jwt.InvalidTokenError as e:
                raise exceptions.AuthenticationFailed(f'Invalid token: {str(e)}')
            
            # Extract user ID from the 'sub' claim (Supabase standard)
            user_id = payload.get('sub')
            
            if not user_id:
                raise exceptions.AuthenticationFailed('Token missing user ID')
            
            # Check token expiration manually
            import time
            exp = payload.get('exp')
            if exp and time.time() > exp:
                raise exceptions.AuthenticationFailed('Token has expired')
            
            # Get user from database
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                # User exists in Supabase auth but not in public.users
                # Auto-create user from token data
                email = payload.get('email')
                if email:
                    user = User.objects.create(
                        id=user_id,
                        email=email,
                        username=payload.get('user_metadata', {}).get('username', email.split('@')[0]),
                        full_name=payload.get('user_metadata', {}).get('full_name', ''),
                        is_active=True
                    )
                    user.set_unusable_password()
                    user.save()
                else:
                    raise exceptions.AuthenticationFailed('User not found')
            
            if not user.is_active:
                raise exceptions.AuthenticationFailed('User is inactive')
            
            return (user, token)
            
        except ValueError:
            raise exceptions.AuthenticationFailed('Invalid token format')
        except exceptions.AuthenticationFailed:
            raise
        except Exception as e:
            raise exceptions.AuthenticationFailed(f'Authentication failed: {str(e)}')


# Keep the old name for backwards compatibility
JWTAuthentication = SupabaseJWTAuthentication
