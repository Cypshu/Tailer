# Auth Flow Runtime Verification Test Plan

> Archived manual plan from 2026-07-04. Unchecked cases are not test evidence; use the active testing guide.

## Overview
This document outlines the comprehensive test plan for verifying the auth scaffolding works end-to-end.

## Environment Setup
```bash
cd Tailer
docker-compose up --build
# Wait for all services to be healthy
```

## Test Cases

### Test 1: Admin Login
**Goal:** Verify admin user can login and receive a valid JWT token

**Steps:**
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "organizer@hackathon.dev",
    "password": "Hackathon Organizer"
  }'
```

**Expected Response:**
```json
{
  "access_token": "<JWT_TOKEN>",
  "token_type": "bearer",
  "user_id": "user_3",
  "email": "organizer@hackathon.dev",
  "name": "Hackathon Organizer",
  "role": "admin"
}
```

**Acceptance Criteria:**
- ✓ Returns 200 status
- ✓ Contains valid JWT token
- ✓ Token type is "bearer"
- ✓ Role is "admin"

---

### Test 2: User Login
**Goal:** Verify regular user can login

**Steps:**
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "team_alpha@hackathon.dev",
    "password": "Team Alpha"
  }'
```

**Expected Response:**
```json
{
  "access_token": "<JWT_TOKEN>",
  "token_type": "bearer",
  "user_id": "user_1",
  "email": "team_alpha@hackathon.dev",
  "name": "Team Alpha",
  "role": "user"
}
```

**Acceptance Criteria:**
- ✓ Returns 200 status
- ✓ Contains valid JWT token
- ✓ Role is "user"

---

### Test 3: Invalid Credentials
**Goal:** Verify login fails with wrong password

**Steps:**
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "organizer@hackathon.dev",
    "password": "wrong_password"
  }'
```

**Expected Response:**
- ✓ Returns 401 status
- ✓ Error message: "Invalid credentials"

---

### Test 4: Admin Access to Admin Routes
**Goal:** Verify admin token can access protected admin routes

**Steps:**
```bash
# Use the admin token from Test 1
TOKEN="<JWT_FROM_TEST_1>"

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/admin/dashboard/stats
```

**Expected Response:**
```json
{
  "active_keys": <number>,
  "total_tokens_used": <number>,
  "total_cost_estimated": <float>,
  "active_users": <number>,
  "total_requests": <number>
}
```

**Acceptance Criteria:**
- ✓ Returns 200 status
- ✓ Returns dashboard statistics
- ✓ No authentication error

---

### Test 5: User Denied from Admin Routes
**Goal:** Verify non-admin user cannot access admin routes

**Steps:**
```bash
# Use the user token from Test 2
TOKEN="<JWT_FROM_TEST_2>"

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/admin/dashboard/stats
```

**Expected Response:**
- ✓ Returns 403 status
- ✓ Error message: "Admin access required"

---

### Test 6: Admin Can Access User Routes
**Goal:** Verify admin user can also access user routes

**Steps:**
```bash
# Use the admin token from Test 1
TOKEN="<JWT_FROM_TEST_1>"

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/user/me
```

**Expected Response:**
```json
{
  "id": "user_3",
  "email": "organizer@hackathon.dev",
  "name": "Hackathon Organizer",
  "role": "admin",
  "created_at": "2026-06-30T09:00:00Z"
}
```

**Acceptance Criteria:**
- ✓ Returns 200 status
- ✓ Returns current user info

---

### Test 7: User Can Access User Routes
**Goal:** Verify user can access their own routes

**Steps:**
```bash
# Use the user token from Test 2
TOKEN="<JWT_FROM_TEST_2>"

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/user/me
```

**Expected Response:**
```json
{
  "id": "user_1",
  "email": "team_alpha@hackathon.dev",
  "name": "Team Alpha",
  "role": "user",
  "created_at": "2026-07-01T10:00:00Z"
}
```

**Acceptance Criteria:**
- ✓ Returns 200 status
- ✓ Returns correct user info

---

### Test 8: User Keys Access
**Goal:** Verify user can access their API keys

**Steps:**
```bash
# Use the user token from Test 2
TOKEN="<JWT_FROM_TEST_2>"

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/user/keys
```

**Expected Response:**
Array of SubApiKey objects for this user

**Acceptance Criteria:**
- ✓ Returns 200 status
- ✓ Returns only keys owned by this user

---

### Test 9: User Stats Access
**Goal:** Verify user can access their usage stats

**Steps:**
```bash
# Use the user token from Test 2
TOKEN="<JWT_FROM_TEST_2>"

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/user/stats
```

**Expected Response:**
```json
{
  "api_keys": <number>,
  "total_tokens_used": <number>,
  "estimated_cost": <float>,
  "total_requests": <number>,
  "monthly_token_limit": <number>,
  "monthly_budget": <float>,
  "token_usage_percent": <float>,
  "budget_usage_percent": <float>
}
```

**Acceptance Criteria:**
- ✓ Returns 200 status
- ✓ Returns user statistics

---

### Test 10: Anonymous Access Denied
**Goal:** Verify anonymous requests get proper 401 error

**Steps:**
```bash
# No Authorization header
curl http://localhost:8000/admin/users
```

**Expected Response:**
- ✓ Returns 401 status
- ✓ Error message indicates missing authorization

---

### Test 11: Expired Token Handling (Future)
**Goal:** Verify expired tokens are rejected
**Note:** Tokens expire in 30 minutes, so this test would need to wait

---

### Test 12: Token Format Verification
**Goal:** Verify JWT token structure is correct

**Steps:**
```bash
# Decode token from Test 1 at jwt.io
# Or use:
TOKEN="<JWT_FROM_TEST_1>"
echo $TOKEN | cut -d'.' -f2 | base64 -d | jq .
```

**Expected Payload:**
```json
{
  "sub": "user_3",
  "exp": <future_timestamp>,
  "iat": <current_timestamp>
}
```

**Acceptance Criteria:**
- ✓ Contains `sub` (subject/user_id)
- ✓ Contains `exp` (expiration timestamp)
- ✓ Contains `iat` (issued at timestamp)

---

## Test Results Summary

| Test | Status | Notes |
|------|--------|-------|
| 1. Admin Login | [ ] | |
| 2. User Login | [ ] | |
| 3. Invalid Credentials | [ ] | |
| 4. Admin Access to Admin Routes | [ ] | |
| 5. User Denied from Admin Routes | [ ] | |
| 6. Admin Can Access User Routes | [ ] | |
| 7. User Can Access User Routes | [ ] | |
| 8. User Keys Access | [ ] | |
| 9. User Stats Access | [ ] | |
| 10. Anonymous Access Denied | [ ] | |
| 11. Expired Token (Future) | N/A | Requires wait |
| 12. Token Format | [ ] | |

---

## Acceptance Criteria Summary

For Task 2 to be marked complete, all of the following must be true:

1. ✓ Login endpoint returns valid JWT tokens for mock users
2. ✓ Admin users can access admin routes
3. ✓ Non-admin users are denied (403) from admin routes
4. ✓ All users can access user routes with valid token
5. ✓ Anonymous access gets 401 error
6. ✓ Token format is valid JWT with correct claims
7. ✓ Auth flow works end-to-end with current frontend

---

## Frontend Integration Testing

Once backend tests pass, verify frontend integration:

1. Go to http://localhost:3000/login
2. Login with `organizer@hackathon.dev` / `Hackathon Organizer`
3. Should redirect to `/admin`
4. Admin dashboard should load with stats
5. Logout button should clear token and redirect to login
6. Login as user account
7. Should redirect to `/user/dashboard`
8. User dashboard should load with personal stats

---

## Notes

- All endpoints use Bearer token in `Authorization` header
- Header format: `Authorization: Bearer <JWT_TOKEN>`
- Demo credentials match `backend/app/mock_data.py`
- Auth imports were fixed to use `Header()` instead of `HTTPBearer()` for compatibility with the current FastAPI dependency stack
