# Sub-API Key Usage Examples

Quick reference for using TAILER Sub-API keys to make runtime requests.

## Available Demo Keys

### Team Alpha
```
Key: tailer_sub_xxxxxxxxxxxxx1
Allowed Models: gpt-4o-mini, gpt-4-turbo
Monthly Budget: €50
```

### Team Beta
```
Key: tailer_sub_xxxxxxxxxxxxx2
Allowed Models: gpt-4o-mini
Monthly Budget: €25
```

### Organizer (Full Access)
```
Key: tailer_sub_xxxxxxxxxxxxx3
Allowed Models: gpt-4o-mini, gpt-4-turbo, gpt-4-preview
Monthly Budget: €500
```

---

## curl Examples

### 1. Simple Request (Team Alpha)

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer tailer_sub_xxxxxxxxxxxxx1" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "user", "content": "What is 2+2?"}
    ],
    "max_tokens": 100
  }'
```

### 2. Request with Team Beta Key

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer tailer_sub_xxxxxxxxxxxxx2" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "user", "content": "Explain quantum computing in 2 sentences"}
    ],
    "max_tokens": 200
  }'
```

### 3. Forbidden Model (Will Fail - 403)

```bash
# Team Beta trying to use gpt-4-turbo (not allowed)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer tailer_sub_xxxxxxxxxxxxx2" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4-turbo",
    "messages": [
      {"role": "user", "content": "Hello"}
    ]
  }'

# Response: 403 Forbidden
# "Model gpt-4-turbo not allowed for this key"
```

### 4. Invalid Key (Will Fail - 401)

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer invalid_key_xyz" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "user", "content": "Hello"}
    ]
  }'

# Response: 401 Unauthorized
# "Invalid or inactive API key"
```

---

## Python Examples

### Basic Request

```python
import requests

url = "http://localhost:8000/v1/chat/completions"
headers = {
    "Authorization": "Bearer tailer_sub_xxxxxxxxxxxxx1",
    "Content-Type": "application/json"
}
data = {
    "model": "gpt-4o-mini",
    "messages": [
        {"role": "user", "content": "What is Python?"}
    ],
    "max_tokens": 150
}

response = requests.post(url, headers=headers, json=data)
result = response.json()

print(f"Status: {response.status_code}")
print(f"Response: {result}")

# Access response data
if response.status_code == 200:
    choice = result['choices'][0]
    message = choice['message']['content']
    usage = result['usage']
    
    print(f"Message: {message}")
    print(f"Tokens used: {usage['total_tokens']}")
```

### Reusable Client Class

```python
import requests
from typing import Optional, List

class TailerClient:
    def __init__(self, base_url: str = "http://localhost:8000", subkey: str = ""):
        self.base_url = base_url
        self.subkey = subkey
    
    def chat_completions(
        self,
        messages: List[dict],
        model: str = "gpt-4o-mini",
        max_tokens: int = 100,
    ) -> Optional[dict]:
        """Send a chat completion request."""
        
        headers = {
            "Authorization": f"Bearer {self.subkey}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=10
            )
            return response.json(), response.status_code
        except Exception as e:
            print(f"Error: {e}")
            return None, None

# Usage
client = TailerClient(subkey="tailer_sub_xxxxxxxxxxxxx1")
result, status = client.chat_completions(
    messages=[{"role": "user", "content": "Hello!"}],
    model="gpt-4o-mini"
)

if status == 200:
    print(result['choices'][0]['message']['content'])
else:
    print(f"Error: {status} - {result.get('detail')}")
```

---

## Response Format

All successful responses follow the OpenAI API format:

```json
{
  "id": "chatcmpl-xyz123",
  "model": "gpt-4o-mini",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "2+2 equals 4."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 8,
    "total_tokens": 23
  }
}
```

---

## Error Responses

### 401 Unauthorized
```json
{
  "detail": "Invalid or inactive API key"
}
```
**Cause:** Missing key, invalid key, or revoked key.

### 403 Forbidden
```json
{
  "detail": "Model gpt-4-turbo not allowed for this key"
}
```
**Cause:** Your key's `allowed_models` list doesn't include the requested model.

### 400 Bad Request
```json
{
  "detail": "request body type is not json"
}
```
**Cause:** Malformed request or missing Content-Type header.

---

## Running the Test Script

```bash
cd C:\Users\Cypsa\Desktop\Hackathon\Tailer

# Make sure backend is running
./start.sh  # or ./start.cmd on Windows

# In another terminal, run the test script
python test_subkey_runtime.py
```

Expected output:
```
🚀🚀🚀...
TAILER Sub-API Key Runtime Tests
🚀🚀🚀...

Backend URL: http://localhost:8000
Demo keys loaded: 3 (team_alpha, team_beta, organizer)

======================================================================
TEST 1: Valid Request with Team Alpha Key
======================================================================
🔑 Using: Team Alpha Hackathon Key
   Model: gpt-4o-mini (allowed)
   Message: 'What is 2+2?'

✅ SUCCESS (HTTP 200)
   Response ID: chatcmpl-xyz123
   Model: gpt-4o-mini

   📊 Usage:
      Prompt tokens: 15
      Completion tokens: 8
      Total tokens: 23

   💬 Assistant response: 2+2 equals 4.
```

---

## Dashboard: View Your Keys

1. Log in: http://localhost:3000/login
2. Use credentials:
   - Email: `team_alpha@hackathon.dev`
   - Password: `team_alpha` (matches email for demo)

3. Go to: **User Dashboard** → **My Keys**
4. You'll see all your Sub-API keys with:
   - Key ID
   - Allowed models
   - Status
   - Creation date
   - Expiration date

---

## Next Steps

- Modify `test_subkey_runtime.py` to test your own prompts
- Integrate the Tailer client into your application
- Monitor usage in the admin dashboard
- Create new keys via the admin panel (if you're an admin)
