# Authentication Implementation Summary

> Archived snapshot from 2026-07-04. It contains claims later found to be stale; use the active backend README and testing guide.

## What Was Implemented

### 1. JWT-Based Authentication (`backend/app/auth.py`)
- Password hashing with bcrypt via passlib
- JWT token generation and validation using python-jose
- Token expiration (30 minutes by default)
- Constants for algorithm (HS256) and secret key management

**Key Functions:**
- `verify_password()` - Compare plain password against bcrypt hash
- `get_password_hash()` - Hash a password
- `create_access_token()` - Generate JWT token
- `decode_access_token()` - Validate and decode JWT token

### 2. Login Endpoint (`backend/app/api/auth.py`)
- `POST /api/auth/login` - Accepts email and password
- Returns access token, token type, user info on success
- For MVP: Uses user's name as password (plaintext for testing)
- In production: Would compare against stored password hashes

**Response Format:**
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "user_id": "user_1",
  "email": "organizer@hackathon.dev",
  "name": "Hackathon Organizer",
  "role": "admin"
}
```

### 3. Route Protection (`backend/app/api/`)

**User Routes (`user.py`):**
- Added `get_current_user_id()` dependency that:
  - Extracts Bearer token from Authorization header
  - Validates JWT token
  - Returns user ID if valid, raises 401 if invalid
- All `/user/*` endpoints now require valid token

**Admin Routes (`admin.py`):**
- Added `get_admin_user_id()` dependency that:
  - Validates JWT token like `get_current_user_id()`
  - Checks user role is "admin"
  - Returns 403 if user is not admin
- All `/admin/*` endpoints now require admin token

### 4. Login Frontend Page (`frontend/app/login/page.tsx`)
- Email and password form
- Stores token and user info in localStorage on success
- Auto-redirects to `/admin` for admins or `/user/dashboard` for regular users
- Error messages for failed login attempts
- Demo credentials displayed for easy testing

### 5. Frontend API Client Updates (`frontend/lib/api.ts`)
- `getAuthHeaders()` - Extracts Bearer token from localStorage
- Auto-includes `Authorization: Bearer <token>` in all requests
- Auto-redirects to `/login` on 401 (token expired/invalid)
- Automatic token injection for all API calls

### 6. Environment Configuration (`.env.example`)
Added JWT settings:
```
JWT_SECRET_KEY=your-jwt-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=30
```

## Security Properties

### Current (MVP)
- ✓ Passwords not stored (using name as password for testing)
- ✓ JWT tokens with expiration
- ✓ Bearer token required for all protected endpoints
- ✓ Role-based access control (admin check)
- ✓ CORS configured for frontend

### Not Yet Implemented (Future)
- Password hashing at rest (would hash before storing)
- Token refresh mechanism
- Rate limiting on login endpoint
- Login attempt auditing
- Encrypted secret key storage

## Demo Credentials

The MVP uses the mock user data with their names as passwords:

**Admin User:**
- Email: `organizer@hackathon.dev`
- Password: `Hackathon Organizer`
- Role: `admin`

**Regular User:**
- Email: `team_alpha@hackathon.dev`
- Password: `Team Alpha`
- Role: `user`

## Testing the Auth Flow

### 1. Login via Frontend
1. Go to http://localhost:3000/login
2. Enter email: `organizer@hackathon.dev`
3. Enter password: `Hackathon Organizer`
4. Click "Login"
5. Should redirect to `/admin`

### 2. Login via API
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"organizer@hackathon.dev","password":"Hackathon Organizer"}'
```

### 3. Access Protected Endpoint
```bash
# Get token first
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"organizer@hackathon.dev","password":"Hackathon Organizer"}' \
  | jq -r '.access_token')

# Use token
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/admin/dashboard/stats
```

## Token Structure

The JWT token contains:
```json
{
  "sub": "user_1",           // Subject (user ID)
  "exp": 1234567890,         // Expiration timestamp
  "iat": 1234567200          // Issued at timestamp
}
```

## What's Different Between User and Admin Routes

| Aspect | User Routes | Admin Routes |
|--------|------------|--------------|
| Endpoint Prefix | `/user` | `/admin` |
| Required Token | Yes | Yes |
| Role Check | None (any authenticated) | Admin only |
| 401 on Invalid Token | Yes | Yes |
| 403 on Wrong Role | N/A | Yes |

## Next Steps

The auth implementation is complete for the MVP. Future tasks:
1. **Backend Persistence** - Move from in-memory to database-backed users/keys
2. **Runtime Protection** - Apply same auth to `/v1/chat/completions` endpoint
3. **Frontend Truthfulness** - Update UI to show actual auth status
4. **Secret Handling** - Implement safe key rotation and storage
