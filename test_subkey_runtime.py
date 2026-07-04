#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for TAILER Sub-API key runtime requests.

Demonstrates:
1. Valid request with allowed model
2. Unauthorized key
3. Forbidden model (not allowed for key)
4. Response structure and usage tracking
"""

import requests
import json
import time
import sys
import io
from typing import Optional

if sys.stdout.encoding and 'utf' not in sys.stdout.encoding.lower():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://localhost:8000"

# Available demo keys from mock_data.py
DEMO_KEYS = {
    "team_alpha": {
        "key": "tailer_sub_xxxxxxxxxxxxx1",
        "name": "Team Alpha Hackathon Key",
        "allowed_models": ["gpt-4o-mini", "gpt-4-turbo"],
    },
    "team_beta": {
        "key": "tailer_sub_xxxxxxxxxxxxx2",
        "name": "Team Beta Hackathon Key",
        "allowed_models": ["gpt-4o-mini"],
    },
    "organizer": {
        "key": "tailer_sub_xxxxxxxxxxxxx3",
        "name": "Organizer Full Access",
        "allowed_models": ["gpt-4o-mini", "gpt-4-turbo", "gpt-4-preview"],
    },
}


def make_runtime_request(
    subkey: str,
    model: str,
    message: str,
    max_tokens: int = 100,
) -> Optional[dict]:
    """Make a request to the /v1/chat/completions endpoint."""

    headers = {
        "Authorization": f"Bearer {subkey}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "max_tokens": max_tokens,
    }

    try:
        response = requests.post(
            f"{BASE_URL}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=10,
        )
        return response.json(), response.status_code
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Could not connect to TAILER backend at {BASE_URL}")
        print("   Make sure the backend is running: ./start.sh or ./start.cmd")
        return None, None
    except Exception as e:
        print(f"[ERROR] {e}")
        return None, None


def test_valid_request():
    """Test 1: Valid request with Team Alpha key."""
    print("\n" + "=" * 70)
    print("TEST 1: Valid Request with Team Alpha Key")
    print("=" * 70)

    key_info = DEMO_KEYS["team_alpha"]
    print(f"[KEY] Using: {key_info['name']}")
    print(f"   Model: gpt-4o-mini (allowed)")
    print(f"   Message: 'What is 2+2?'")

    response, status_code = make_runtime_request(
        subkey=key_info["key"],
        model="gpt-4o-mini",
        message="What is 2+2?",
    )

    if response is None:
        return

    if status_code == 200:
        print(f"\n[OK] SUCCESS (HTTP {status_code})")
        print(f"   Response ID: {response.get('id')}")
        print(f"   Model: {response.get('model')}")

        usage = response.get('usage', {})
        print(f"\n   [USAGE] Stats:")
        print(f"      Prompt tokens: {usage.get('prompt_tokens')}")
        print(f"      Completion tokens: {usage.get('completion_tokens')}")
        print(f"      Total tokens: {usage.get('total_tokens')}")

        choices = response.get('choices', [])
        if choices:
            content = choices[0].get('message', {}).get('content')
            print(f"\n   [RESP] Assistant response: {content}")
    else:
        print(f"\n[FAIL] FAILED (HTTP {status_code})")
        print(f"   Error: {response.get('detail', 'Unknown error')}")


def test_invalid_key():
    """Test 2: Request with invalid/revoked key."""
    print("\n" + "=" * 70)
    print("TEST 2: Invalid API Key")
    print("=" * 70)

    print(f"[KEY] Using: invalid_key_xyz")
    print(f"   Expected: 401 Unauthorized")

    response, status_code = make_runtime_request(
        subkey="invalid_key_xyz",
        model="gpt-4o-mini",
        message="Hello",
    )

    if response is None:
        return

    if status_code == 401:
        print(f"\n[OK] CORRECTLY REJECTED (HTTP {status_code})")
        print(f"   Error: {response.get('detail')}")
    else:
        print(f"\n[FAIL] Unexpected response (HTTP {status_code})")
        print(f"   Response: {json.dumps(response, indent=2)}")


def test_forbidden_model():
    """Test 3: Using a model not allowed for the key."""
    print("\n" + "=" * 70)
    print("TEST 3: Forbidden Model (not in key's allowed_models)")
    print("=" * 70)

    key_info = DEMO_KEYS["team_beta"]
    print(f"[KEY] Using: {key_info['name']}")
    print(f"   Allowed models: {', '.join(key_info['allowed_models'])}")
    print(f"   Attempting model: gpt-4-turbo (NOT ALLOWED)")
    print(f"   Expected: 403 Forbidden")

    response, status_code = make_runtime_request(
        subkey=key_info["key"],
        model="gpt-4-turbo",
        message="Hello",
    )

    if response is None:
        return

    if status_code == 403:
        print(f"\n[OK] CORRECTLY REJECTED (HTTP {status_code})")
        print(f"   Error: {response.get('detail')}")
    else:
        print(f"\n[FAIL] Unexpected response (HTTP {status_code})")
        print(f"   Response: {json.dumps(response, indent=2)}")


def test_all_keys():
    """Test 4: Make a request with each demo key."""
    print("\n" + "=" * 70)
    print("TEST 4: All Demo Keys")
    print("=" * 70)

    for team, key_info in DEMO_KEYS.items():
        print(f"\n  Testing {team.upper()}: {key_info['name']}")

        response, status_code = make_runtime_request(
            subkey=key_info["key"],
            model=key_info["allowed_models"][0],
            message="Hi, what's your name?",
        )

        if response and status_code == 200:
            print(f"  [OK] Success - {response.get('model')} responded")
        else:
            print(f"  [FAIL] Failed - HTTP {status_code}")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("TAILER Sub-API Key Runtime Tests")
    print("=" * 70)

    print(f"\nBackend URL: {BASE_URL}")
    print("Demo keys loaded: 3 (team_alpha, team_beta, organizer)")

    # Run tests
    test_valid_request()
    time.sleep(1)

    test_invalid_key()
    time.sleep(1)

    test_forbidden_model()
    time.sleep(1)

    test_all_keys()

    print("\n" + "=" * 70)
    print("Tests Complete!")
    print("=" * 70)
    print("\n[INFO] Next steps:")
    print("   1. Check mock_data.py to see all available keys")
    print("   2. Modify model names to test different models")
    print("   3. Use these keys in your own application")
    print("   4. Monitor usage in the admin dashboard")


if __name__ == "__main__":
    main()
