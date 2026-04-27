#!/usr/bin/env python3
"""
Webhook Inspector — Self-hosted, privacy-first webhook capture and analysis.

Run:
    uvicorn main:app --host 0.0.0.0 --port 9120 --reload

Environment:
    LOCAL_LLM_URL   → local model endpoint (default: http://127.0.0.1:8081/v1/chat/completions)
    LOCAL_LLM_MODEL → model name (default: qwen-local)
    INSPECTOR_PORT  → port to run on (default: 9120)
"""

import time
import csv
import io
import aiohttp
import asyncio
import json
import os
import concurrent.futures
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import storage
import inspector


import stripe
import license

# Stripe config
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
stripe.api_key = STRIPE_SECRET_KEY
SUCCESS_URL = os.getenv("SUCCESS_URL", "https://webcatch.dev/success?session_id={CHECKOUT_SESSION_ID}")
CANCEL_URL = os.getenv("CANCEL_URL", "https://webcatch.dev/")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.getenv("INSPECTOR_PORT", "9120"))
HOST = os.getenv("INSPECTOR_HOST", "0.0.0.0")

# Track active endpoints in memory (endpoint_id → created_at)
active_endpoints: dict[str, str] = {}

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    storage.init_endpoint_config()
    # Restore endpoint IDs from DB
    for eid in storage.get_all_endpoint_ids():
        active_endpoints[eid] = {"created": True}
    yield
    # cleanup if needed


app = FastAPI(title="Webhook Inspector", version="0.4.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard_root():
    html_path = os.path.join(APP_DIR, "static", "dashboard.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Webhook Inspector</h1><p>Dashboard HTML not found.</p>"

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    html_path = os.path.join(APP_DIR, "static", "dashboard.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Webhook Inspector</h1><p>Dashboard HTML not found.</p>"


# ---------------------------------------------------------------------------
# API: Endpoints management
# ---------------------------------------------------------------------------

@app.post("/api/endpoints")
async def create_endpoint():
    endpoint_id = storage.create_endpoint()
    active_endpoints[endpoint_id] = {"created": True}
    return {
        "endpoint_id": endpoint_id,
        "webhook_url": f"http://{HOST}:{PORT}/wh/{endpoint_id}",
        "dashboard_url": f"http://{HOST}:{PORT}/#/endpoint/{endpoint_id}",
    }


@app.get("/api/endpoints")
async def list_endpoints():
    endpoints = []
    for eid in list(active_endpoints.keys()):
        ep = storage.get_endpoint(eid)
        endpoints.append({
            "endpoint_id": eid,
            "enabled": ep.get("enabled", True),
            "webhook_url": f"http://{HOST}:{PORT}/wh/{eid}",
        })
    return {"endpoints": endpoints}


@app.post("/api/endpoints/{endpoint_id}/toggle")
async def toggle_endpoint(endpoint_id: str):
    ep = storage.get_endpoint(endpoint_id)
    new_state = not ep.get("enabled", True)
    storage.set_endpoint_enabled(endpoint_id, new_state)
    return {"endpoint_id": endpoint_id, "enabled": new_state}


# ---------------------------------------------------------------------------
# API: Stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
async def get_stats():
    return storage.get_stats()


# ---------------------------------------------------------------------------
# API: Webhook capture (the core magic)
# ---------------------------------------------------------------------------

@app.api_route("/wh/{endpoint_id}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def capture_webhook(endpoint_id: str, request: Request):
    ep = storage.get_endpoint(endpoint_id)
    if not ep.get("enabled", True):
        return JSONResponse(
            content={"status": "disabled", "message": "This endpoint is currently disabled."},
            status_code=503,
        )

    if endpoint_id not in active_endpoints:
        active_endpoints[endpoint_id] = {"created": True}

    start_time = time.time()

    # Read body
    body: Optional[bytes] = None
    try:
        body = await request.body()
        if len(body) == 0:
            body = None
    except Exception:
        body = None

    # Extract headers
    headers = dict(request.headers)

    # Query params
    query_params = dict(request.query_params)

    # Client IP
    client_ip = request.client.host if request.client else None

    # Filter rules check
    config = storage.get_endpoint_config(endpoint_id)
    if config:
        rules = config.get("filter_rules") or {}
        if rules:
            # Method filter
            allowed_methods = rules.get("allowed_methods")
            if allowed_methods and request.method not in allowed_methods:
                return JSONResponse(
                    content={"status": "filtered", "reason": "method_not_allowed"},
                    status_code=200,
                )
            # Header required filter
            required_header = rules.get("required_header")
            if required_header:
                key, val = required_header.split(":", 1) if ":" in required_header else (required_header, None)
                if key not in headers:
                    return JSONResponse(content={"status": "filtered", "reason": "missing_header"}, status_code=200)
                if val and headers.get(key) != val:
                    return JSONResponse(content={"status": "filtered", "reason": "header_mismatch"}, status_code=200)
            # Body contains filter
            body_contains = rules.get("body_contains")
            if body_contains:
                body_text = body.decode("utf-8", errors="replace") if body else ""
                if body_contains not in body_text:
                    return JSONResponse(content={"status": "filtered", "reason": "body_no_match"}, status_code=200)

    # Store it
    latency_ms = (time.time() - start_time) * 1000
    webhook_id = storage.store_webhook(
        endpoint_id=endpoint_id,
        method=request.method,
        url=str(request.url),
        headers=headers,
        body=body,
        query_params=query_params,
        client_ip=client_ip,
        latency_ms=round(latency_ms, 2),
    )

    # Retention cleanup
    if config and config.get("retention_count"):
        storage.apply_retention(endpoint_id, config["retention_count"])

    # Fire-and-forget LLM analysis with timing
    body_text = body.decode("utf-8", errors="replace") if body else None
    asyncio.create_task(
        _analyze_and_store(webhook_id, request.method, str(request.url), headers, body_text, query_params)
    )

    # Fire-and-forget forwarding if configured
    if config and config.get("forward_url"):
        asyncio.create_task(
            _forward_webhook(webhook_id, request.method, config["forward_url"], headers, body, query_params, transform_script=config.get("transform_script"))
        )

    # Broadcast to all connected WebSocket clients
    webhook_data = {
        "type": "new_webhook",
        "webhook": {
            "id": webhook_id,
            "endpoint_id": endpoint_id,
            "method": request.method,
            "url": str(request.url),
            "headers": headers,
            "body": body_text,
            "query_params": query_params,
            "client_ip": client_ip,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "analyzed": 0,
            "analysis": None,
            "latency_ms": round(latency_ms, 2),
        },
    }
    asyncio.create_task(manager.broadcast(webhook_data))

    # Check for custom response config
    if config:
        resp_headers = config.get("response_headers") or {}
        resp_body = config.get("response_body")
        status_code = config.get("status_code", 200)
        return JSONResponse(
            content=resp_body if resp_body else {"status": "captured", "webhook_id": webhook_id},
            status_code=status_code,
            headers=resp_headers,
        )

    # Return a generic 200 so the sender doesn't error out
    return JSONResponse(
        content={"status": "captured", "webhook_id": webhook_id},
        status_code=200,
    )


async def _analyze_and_store(
    webhook_id: str,
    method: str,
    url: str,
    headers: dict,
    body: Optional[str],
    query_params: dict,
) -> None:
    """Background task: run local LLM analysis and store result."""
    start = time.time()
    try:
        analysis = await inspector.analyze_webhook(method, url, headers, body, query_params)
        elapsed_ms = (time.time() - start) * 1000
        storage.update_analysis(webhook_id, analysis, analysis_time_ms=round(elapsed_ms, 2))
        # Broadcast analysis update
        await manager.broadcast({
            "type": "analysis_update",
            "webhook_id": webhook_id,
            "analysis": analysis,
            "analysis_time_ms": round(elapsed_ms, 2),
        })
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        storage.update_analysis(webhook_id, f"Analysis failed: {e}", analysis_time_ms=round(elapsed_ms, 2))
        await manager.broadcast({
            "type": "analysis_update",
            "webhook_id": webhook_id,
            "analysis": f"Analysis failed: {e}",
            "analysis_time_ms": round(elapsed_ms, 2),
        })


# Thread pool for running user transform scripts
_transform_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="transform")


def _run_transform_sync(script: str, method: str, url: str, headers: dict, body: Optional[str], query: dict) -> tuple:
    """Run a user transform script in a restricted sandbox. Returns (method, url, headers, body, query, error)."""
    if not script or not script.strip():
        return method, url, headers, body, query, None

    safe_globals = {
        "__builtins__": {
            "len": len, "str": str, "int": int, "float": float,
            "bool": bool, "dict": dict, "list": list, "tuple": tuple, "set": set,
            "json": __import__("json"),
            "re": __import__("re"),
            "datetime": __import__("datetime"),
            "print": lambda *a, **k: None,
            "type": type, "isinstance": isinstance, "hasattr": hasattr, "getattr": getattr,
            "enumerate": enumerate, "range": range, "zip": zip, "map": map, "filter": filter,
            "sum": sum, "min": min, "max": max, "abs": abs, "round": round,
        }
    }

    locals_dict = {
        "method": method,
        "url": url,
        "headers": dict(headers),
        "body": body,
        "query": dict(query),
    }

    try:
        exec(script, safe_globals, locals_dict)
        return (
            locals_dict.get("method", method),
            locals_dict.get("url", url),
            locals_dict.get("headers", headers),
            locals_dict.get("body", body),
            locals_dict.get("query", query),
            None,
        )
    except Exception as e:
        return method, url, headers, body, query, str(e)


async def _forward_webhook(
    webhook_id: str,
    method: str,
    forward_url: str,
    headers: dict,
    body: Optional[bytes],
    query_params: dict,
    transform_script: Optional[str] = None,
) -> None:
    """Forward captured webhook to another URL with retry and optional transform."""
    max_retries = 3
    base_delay = 1.0

    # Decode body for transform
    body_text = body.decode("utf-8", errors="replace") if body else None

    # Run transform if configured
    if transform_script and transform_script.strip():
        loop = asyncio.get_event_loop()
        try:
            t_method, t_url, t_headers, t_body, t_query, t_error = await asyncio.wait_for(
                loop.run_in_executor(
                    _transform_executor,
                    _run_transform_sync,
                    transform_script,
                    method,
                    forward_url,
                    dict(headers),
                    body_text,
                    dict(query_params),
                ),
                timeout=5.0,
            )
            if t_error:
                storage.update_forward_status(webhook_id, 0, f"Transform error: {t_error}")
                await manager.broadcast({
                    "type": "forward_update",
                    "webhook_id": webhook_id,
                    "forward_status": 0,
                })
                return
            method = t_method
            forward_url = t_url
            headers = t_headers
            body_text = t_body
            query_params = t_query
            body = t_body.encode("utf-8") if t_body else None
        except asyncio.TimeoutError:
            storage.update_forward_status(webhook_id, 0, "Transform error: script timed out after 5s")
            await manager.broadcast({
                "type": "forward_update",
                "webhook_id": webhook_id,
                "forward_status": 0,
            })
            return
        except Exception as e:
            storage.update_forward_status(webhook_id, 0, f"Transform error: {e}")
            await manager.broadcast({
                "type": "forward_update",
                "webhook_id": webhook_id,
                "forward_status": 0,
            })
            return

    for attempt in range(1, max_retries + 1):
        try:
            target = forward_url
            if query_params:
                separator = "&" if "?" in forward_url else "?"
                target += separator + "&".join(f"{k}={v}" for k, v in query_params.items())
            fwd_headers = {k: v for k, v in headers.items() if k.lower() not in ["host", "content-length", "transfer-encoding", "connection"]}
            fwd_body = body
            async with aiohttp.ClientSession() as session:
                async with session.request(method, target, headers=fwd_headers, data=fwd_body) as resp:
                    resp_text = await resp.text()
                    storage.update_forward_status(webhook_id, resp.status, resp_text[:2000])
                    await manager.broadcast({
                        "type": "forward_update",
                        "webhook_id": webhook_id,
                        "forward_status": resp.status,
                    })
                    return  # success
        except Exception as e:
            if attempt < max_retries:
                await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
                continue
            # final attempt failed
            storage.update_forward_status(webhook_id, 0, str(e)[:500])
            await manager.broadcast({
                "type": "forward_update",
                "webhook_id": webhook_id,
                "forward_status": 0,
            })


async def _analyze_and_store(
    webhook_id: str,
    method: str,
    url: str,
    headers: dict,
    body: Optional[str],
    query_params: dict,
) -> None:
    """Background task: run local LLM analysis and store result."""
    start = time.time()
    try:
        analysis = await inspector.analyze_webhook(method, url, headers, body, query_params)
        elapsed_ms = (time.time() - start) * 1000
        storage.update_analysis(webhook_id, analysis, analysis_time_ms=round(elapsed_ms, 2))
        # Broadcast analysis update
        await manager.broadcast({
            "type": "analysis_update",
            "webhook_id": webhook_id,
            "analysis": analysis,
            "analysis_time_ms": round(elapsed_ms, 2),
        })
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        storage.update_analysis(webhook_id, f"Analysis failed: {e}", analysis_time_ms=round(elapsed_ms, 2))
        await manager.broadcast({
            "type": "analysis_update",
            "webhook_id": webhook_id,
            "analysis": f"Analysis failed: {e}",
            "analysis_time_ms": round(elapsed_ms, 2),
        })


# ---------------------------------------------------------------------------
# API: Export webhooks (must be before /api/webhooks/{webhook_id})
# ---------------------------------------------------------------------------

def _webhook_to_postman_item(wh: dict) -> dict:
    """Convert a single webhook to a Postman Collection v2.1 item."""
    headers = wh.get("headers") or {}
    query_params = wh.get("query_params") or {}
    body = wh.get("body")
    method = wh.get("method", "GET")
    url = wh.get("url", "")
    
    # Build URL object
    url_obj = {"raw": url, "host": [url]}
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        url_obj = {
            "raw": url,
            "protocol": parsed.scheme,
            "host": [parsed.hostname] if parsed.hostname else [""],
            "port": parsed.port,
            "path": [p for p in parsed.path.split("/") if p],
            "query": [{"key": k, "value": v} for k, v in query_params.items()],
        }
    except Exception:
        pass
    
    # Build header list (skip hop-by-hop)
    header_list = []
    for k, v in headers.items():
        if k.lower() in ["host", "content-length", "transfer-encoding", "connection"]:
            continue
        header_list.append({"key": k, "value": str(v)})
    
    # Build body
    body_obj = None
    if body:
        content_type = headers.get("content-type", headers.get("Content-Type", ""))
        if "json" in content_type.lower():
            try:
                body_obj = {"mode": "raw", "raw": body, "options": {"raw": {"language": "json"}}}
            except Exception:
                body_obj = {"mode": "raw", "raw": body}
        else:
            body_obj = {"mode": "raw", "raw": body}
    
    item = {
        "name": f"{method} {url[:80]}",
        "request": {
            "method": method,
            "header": header_list,
            "url": url_obj,
            "description": f"Captured at {wh.get('received_at', '')} from {wh.get('client_ip', 'unknown')}",
        },
        "response": [],
    }
    if body_obj:
        item["request"]["body"] = body_obj
    return item


def _webhook_to_curl(wh: dict) -> str:
    """Convert a single webhook to a cURL command."""
    headers = wh.get("headers") or {}
    body = wh.get("body")
    method = wh.get("method", "GET")
    url = wh.get("url", "")
    
    cmd = f'curl -X {method} "{url}"'
    for k, v in headers.items():
        if k.lower() in ["host", "content-length", "transfer-encoding", "connection"]:
            continue
        safe_v = str(v).replace('"', '\\"')
        cmd += f' \\\n  -H "{k}: {safe_v}"'
    if body:
        safe_body = body.replace("'", "'\\''")
        cmd += f" \\\n  -d '{safe_body}'"
    return cmd


@app.get("/api/webhooks/export")
async def export_webhooks(format: str = "json", endpoint_id: Optional[str] = None):
    webhooks = storage.get_webhooks(endpoint_id=endpoint_id, limit=1000)
    for wh in webhooks:
        wh["headers"] = json.loads(wh["headers"]) if wh["headers"] else {}
        wh["query_params"] = json.loads(wh["query_params"]) if wh["query_params"] else {}

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "endpoint_id", "method", "url", "received_at", "client_ip", "latency_ms", "analysis_time_ms", "body"])
        for wh in webhooks:
            writer.writerow([
                wh["id"], wh["endpoint_id"], wh["method"], wh["url"],
                wh["received_at"], wh.get("client_ip", ""),
                wh.get("latency_ms", ""), wh.get("analysis_time_ms", ""),
                wh["body"] or "",
            ])
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=webhooks-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"},
        )
    
    if format == "postman":
        collection = {
            "info": {
                "_postman_id": f"webcatch-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "name": f"Webcatch Export — {endpoint_id or 'All Endpoints'}",
                "description": f"Exported from Webcatch on {datetime.now(timezone.utc).isoformat()}",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [_webhook_to_postman_item(wh) for wh in webhooks],
        }
        return StreamingResponse(
            io.BytesIO(json.dumps(collection, indent=2).encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=webcatch-{endpoint_id or 'all'}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.postman_collection.json"},
        )
    
    if format == "curl":
        commands = [_webhook_to_curl(wh) for wh in webhooks]
        output = "\n\n# ----\n\n".join(commands)
        return StreamingResponse(
            io.BytesIO(output.encode("utf-8")),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=webcatch-{endpoint_id or 'all'}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.sh"},
        )

    return JSONResponse(content={"webhooks": webhooks})


# ---------------------------------------------------------------------------
# API: Webhook retrieval
# ---------------------------------------------------------------------------

@app.get("/api/webhooks")
async def list_webhooks(endpoint_id: Optional[str] = None, limit: int = 100):
    webhooks = storage.get_webhooks(endpoint_id=endpoint_id, limit=limit)
    # Parse JSON fields for the frontend
    for wh in webhooks:
        wh["headers"] = json.loads(wh["headers"]) if wh["headers"] else {}
        wh["query_params"] = json.loads(wh["query_params"]) if wh["query_params"] else {}
    return {"webhooks": webhooks}


@app.get("/api/webhooks/{webhook_id}")
async def get_webhook(webhook_id: str):
    wh = storage.get_webhook(webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    wh["headers"] = json.loads(wh["headers"]) if wh["headers"] else {}
    wh["query_params"] = json.loads(wh["query_params"]) if wh["query_params"] else {}
    return wh


@app.get("/api/webhooks/{webhook_id}/export")
async def export_single_webhook(webhook_id: str, format: str = "curl"):
    wh = storage.get_webhook(webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    wh["headers"] = json.loads(wh["headers"]) if wh["headers"] else {}
    wh["query_params"] = json.loads(wh["query_params"]) if wh["query_params"] else {}
    
    if format == "postman":
        collection = {
            "info": {
                "_postman_id": f"webcatch-single-{webhook_id}",
                "name": f"Webcatch Single — {wh['method']} {wh['url'][:60]}",
                "description": f"Exported from Webcatch on {datetime.now(timezone.utc).isoformat()}",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [_webhook_to_postman_item(wh)],
        }
        return StreamingResponse(
            io.BytesIO(json.dumps(collection, indent=2).encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=webcatch-{webhook_id}.postman_collection.json"},
        )
    
    if format == "curl":
        cmd = _webhook_to_curl(wh)
        return StreamingResponse(
            io.BytesIO(cmd.encode("utf-8")),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=webcatch-{webhook_id}.sh"},
        )
    
    raise HTTPException(status_code=400, detail="Format must be 'postman' or 'curl'")


@app.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str):
    storage.delete_webhook(webhook_id)
    return {"status": "deleted"}


@app.delete("/api/endpoints/{endpoint_id}/webhooks")
async def clear_endpoint(endpoint_id: str):
    storage.delete_all_for_endpoint(endpoint_id)
    return {"status": "cleared"}


# ---------------------------------------------------------------------------
# API: Endpoint response configuration
# ---------------------------------------------------------------------------

@app.get("/api/endpoints/{endpoint_id}/config")
async def get_endpoint_config(endpoint_id: str):
    cfg = storage.get_endpoint_config(endpoint_id)
    if not cfg:
        return {"endpoint_id": endpoint_id, "status_code": 200, "response_headers": {}, "response_body": None, "forward_url": None, "retention_count": 0, "filter_rules": {}, "transform_script": None}
    return cfg


@app.put("/api/endpoints/{endpoint_id}/config")
async def set_endpoint_config(endpoint_id: str, request: Request):
    data = await request.json()
    storage.set_endpoint_config(
        endpoint_id=endpoint_id,
        status_code=data.get("status_code", 200),
        response_headers=data.get("response_headers", {}),
        response_body=data.get("response_body"),
        forward_url=data.get("forward_url"),
        retention_count=data.get("retention_count"),
        filter_rules=data.get("filter_rules"),
        transform_script=data.get("transform_script"),
    )
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# API: Replay webhook
# ---------------------------------------------------------------------------

@app.post("/api/webhooks/{webhook_id}/replay")
async def replay_webhook(webhook_id: str, request: Request):
    wh = storage.get_webhook(webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    data = await request.json() if request.headers.get("content-length") else {}
    target_url = data.get("url") if data else None

    headers = json.loads(wh["headers"]) if wh["headers"] else {}
    body = wh["body"]
    method = wh["method"]
    url = target_url or wh["url"]

    # Remove hop-by-hop headers
    for h in ["host", "content-length", "transfer-encoding", "connection"]:
        headers.pop(h, None)
        headers.pop(h.title(), None)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, data=body.encode("utf-8") if body else None) as resp:
                resp_body = await resp.text()
                return {
                    "status": "replayed",
                    "original_webhook_id": webhook_id,
                    "target_url": url,
                    "response_status": resp.status,
                    "response_body": resp_body[:2000],  # truncate
                }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Replay failed: {e}")


@app.post("/api/bulk-replay")
async def bulk_replay(request: Request):
    data = await request.json()
    webhook_ids = data.get("webhook_ids", [])
    target_url = data.get("url")
    if not webhook_ids:
        raise HTTPException(status_code=400, detail="No webhook_ids provided")

    results = []
    for wh_id in webhook_ids:
        wh = storage.get_webhook(wh_id)
        if not wh:
            results.append({"webhook_id": wh_id, "status": "not_found"})
            continue
        headers = json.loads(wh["headers"]) if wh["headers"] else {}
        body = wh["body"]
        method = wh["method"]
        url = target_url or wh["url"]
        for h in ["host", "content-length", "transfer-encoding", "connection"]:
            headers.pop(h, None)
            headers.pop(h.title(), None)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, headers=headers, data=body.encode("utf-8") if body else None) as resp:
                    resp_body = await resp.text()
                    results.append({
                        "webhook_id": wh_id,
                        "status": "replayed",
                        "target_url": url,
                        "response_status": resp.status,
                    })
        except Exception as e:
            results.append({"webhook_id": wh_id, "status": "error", "error": str(e)})

    return {"replayed": len([r for r in results if r["status"] == "replayed"]), "results": results}


# ---------------------------------------------------------------------------
# API: Test webhook generator
# ---------------------------------------------------------------------------

@app.post("/api/test-webhook")
async def test_webhook(request: Request):
    data = await request.json()
    target_url = data.get("url")
    method = data.get("method", "POST")
    headers = data.get("headers", {})
    body = data.get("body", "")

    if not target_url:
        raise HTTPException(status_code=400, detail="url is required")

    try:
        req_body = None
        if body:
            if isinstance(body, dict):
                req_body = json.dumps(body).encode('utf-8')
                if not headers.get('Content-Type'):
                    headers['Content-Type'] = 'application/json'
            else:
                req_body = body.encode('utf-8')
        async with aiohttp.ClientSession() as session:
            async with session.request(method, target_url, headers=headers, data=req_body) as resp:
                resp_text = await resp.text()
                return {
                    "status": "sent",
                    "target_url": target_url,
                    "response_status": resp.status,
                    "response_body": resp_text[:2000],
                }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Request failed: {e}")


# ---------------------------------------------------------------------------
# API: Diff two webhooks
# ---------------------------------------------------------------------------

@app.get("/api/webhooks/{webhook_a}/diff/{webhook_b}")
async def diff_webhooks(webhook_a: str, webhook_b: str):
    a = storage.get_webhook(webhook_a)
    b = storage.get_webhook(webhook_b)
    if not a or not b:
        raise HTTPException(status_code=404, detail="One or both webhooks not found")

    def normalize(wh):
        return {
            "method": wh["method"],
            "url": wh["url"],
            "headers": json.loads(wh["headers"]) if wh["headers"] else {},
            "body": wh["body"],
            "query_params": json.loads(wh["query_params"]) if wh["query_params"] else {},
        }

    na = normalize(a)
    nb = normalize(b)

    diff = {}
    all_keys = set(na.keys()) | set(nb.keys())
    for key in all_keys:
        if na.get(key) != nb.get(key):
            diff[key] = {"a": na.get(key), "b": nb.get(key)}

    return {
        "webhook_a": webhook_a,
        "webhook_b": webhook_b,
        "diff": diff,
        "identical": len(diff) == 0,
    }


# ---------------------------------------------------------------------------
# API: Signature verification
# ---------------------------------------------------------------------------

@app.post("/api/webhooks/{webhook_id}/verify")
async def verify_webhook_sig(webhook_id: str, request: Request):
    wh = storage.get_webhook(webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    data = await request.json()
    secrets = data.get("secrets", {})
    body = (wh["body"] or "").encode("utf-8")
    headers = json.loads(wh["headers"]) if wh["headers"] else {}

    import signature as sig_module
    result = sig_module.verify_webhook(headers, body, secrets)
    return result


# ---------------------------------------------------------------------------
# WebSocket: Real-time updates
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, handle any incoming messages
            data = await websocket.receive_text()
            # Client can send ping/heartbeat or filter requests
            try:
                msg = json.loads(data)
                if msg.get("action") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Health / Info
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.3.0", "local_llm": inspector.LOCAL_LLM_URL}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)

# ---------------------------------------------------------------------------
# Stripe Checkout & License
# ---------------------------------------------------------------------------

@app.post("/api/checkout")
async def create_checkout():
    if not STRIPE_SECRET_KEY:
        return JSONResponse({"error": "Stripe not configured"}, status_code=500)
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Webcatch Pro License", "description": "Lifetime self-hosted Pro license"},
                    "unit_amount": 3900,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
        )
        return {"url": session.url}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/success", response_class=HTMLResponse)
async def checkout_success(session_id: str = None):
    if not session_id or not STRIPE_SECRET_KEY:
        return "<h1>Missing session</h1><p>Please contact support.</p>"
    try:
        sess = stripe.checkout.Session.retrieve(session_id)
        if sess.payment_status != "paid":
            return "<h1>Payment not completed</h1><p>If you believe this is an error, contact support.</p>"
        
        # Check if we already generated a license for this session
        # (In a real app you'd query by stripe_session_id; here we generate fresh each time for simplicity)
        lic_key = license.create_license(
            email=sess.customer_details.email if sess.customer_details else None,
            stripe_session_id=session_id
        )
        
        return f"""<!DOCTYPE html>
<html><head><title>Webcatch Pro — Success</title>
<style>
body {{ background: #0d1117; color: #c9d1d9; font-family: sans-serif; text-align: center; padding: 80px 20px; }}
h1 {{ color: #58a6ff; }} .key {{ background: #161b22; border: 1px solid #30363d; padding: 16px 24px; border-radius: 8px;
font-family: monospace; font-size: 1.1rem; color: #3fb950; margin: 20px auto; display: inline-block; }}
.btn {{ background: #58a6ff; color: #0d1117; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; display: inline-block; margin-top: 20px; }}
</style></head><body>
<h1>🎉 Welcome to Webcatch Pro!</h1>
<p>Your payment was successful. Here is your license key:</p>
<div class="key">{lic_key}</div>
<p>Copy this key and paste it into your self-hosted Webcatch app under Settings → License.</p>
<a href="/dashboard" class="btn">Open Webcatch</a>
</body></html>"""
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>"


@app.post("/api/license/validate")
async def validate_license(request: Request):
    data = await request.json()
    key = data.get("key", "")
    if license.validate_license(key):
        license.mark_validated(key)
        return {"valid": True}
    return {"valid": False}


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    if not STRIPE_WEBHOOK_SECRET:
        return JSONResponse({"error": "Webhook secret not configured"}, status_code=500)
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        return JSONResponse({"error": "Invalid payload"}, status_code=400)
    except stripe.error.SignatureVerificationError:
        return JSONResponse({"error": "Invalid signature"}, status_code=400)
    
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        if session.payment_status == "paid":
            license.create_license(
                email=session.customer_details.email if session.customer_details else None,
                stripe_session_id=session.id
            )
    return {"status": "ok"}

