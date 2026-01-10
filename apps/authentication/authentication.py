from rest_framework import authentication, exceptions
from .jwt_service import JWTService


class JWTAuthentication(authentication.BaseAuthentication):
    """Custom JWT authentication class for DRF."""
    
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
            
            # Verify token and get user
            user = JWTService.get_user_from_token(token)
            
            return (user, token)
            
        except ValueError:
            raise exceptions.AuthenticationFailed('Invalid token format')
        except Exception as e:
            raise exceptions.AuthenticationFailed(str(e))
