"""
Local LLM analysis for captured webhooks.
Uses the local Qwen endpoint (127.0.0.1:8081) for privacy-first analysis.
"""

import json
import os
from typing import Optional

import aiohttp

LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://127.0.0.1:8081/v1/chat/completions")
MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen-local")


async def analyze_webhook(
    method: str,
    url: str,
    headers: dict,
    body: Optional[str],
    query_params: dict,
) -> str:
    """
    Send the webhook payload to the local model and get a structured analysis.
    """
    # Build a clean prompt
    prompt = _build_prompt(method, url, headers, body, query_params)

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a webhook security and debugging analyst. "
                    "Analyze the provided HTTP request and give a concise summary covering:\n"
                    "1. What service/provider likely sent this\n"
                    "2. Any security concerns (missing signatures, suspicious IPs, etc.)\n"
                    "3. A brief explanation of what the payload represents\n"
                    "4. Suggested response code and any validation steps\n"
                    "Keep your response under 200 words. Be specific and actionable."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 400,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(LOCAL_LLM_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return f"Analysis failed (HTTP {resp.status}): {text[:200]}"
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except aiohttp.ClientConnectorError:
        return "Local LLM unavailable. Ensure the model server is running on port 8081."
    except Exception as e:
        return f"Analysis error: {e}"


def _build_prompt(method: str, url: str, headers: dict, body: Optional[str], query_params: dict) -> str:
    # Sanitize and summarize
    header_str = json.dumps(headers, indent=2, default=str)
    query_str = json.dumps(query_params, indent=2, default=str) if query_params else "{}"
    body_preview = (body or "")[:2000]

    prompt = f"""HTTP Request:
Method: {method}
URL: {url}
Query Parameters: {query_str}
Headers:
{header_str}
Body (truncated to 2000 chars):
{body_preview}
"""
    return prompt
