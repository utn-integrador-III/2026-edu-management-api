from fastapi import HTTPException, Depends
from src.middleware.auth_middleware import verify_token

def require_role(*roles):
      def dependency(user: dict = Depends(verify_token)):
          if user.get('mustChangePassword'):
              raise HTTPException(status_code=403, detail='Password change required')
          if user.get('role') not in roles:
              raise HTTPException(status_code=403, detail='Unauthorized')
          return user
      return dependency
