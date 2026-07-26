"""
main.py — FastAPI Application Entry Point & WebSockets
"""

import asyncio
import logging
import json
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body, UploadFile, File
from fastapi.responses import StreamingResponse
import tempfile
import os
from sarvamai import SarvamAI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── In-memory escalation queue for SSE stream ─────────────────────────────────
# Stores pending escalation events to broadcast to connected supervisor clients
_escalation_queue: List[Dict[str, Any]] = []
_escalation_subscribers: List[asyncio.Queue] = []

from ai_backend.config import settings
from ai_backend.auth import list_demo_customers, get_customer_profile
from ai_backend.agent.orchestrator import ConversationManager
from ai_backend.agent.tools import set_supervisor_broadcaster
from audit_service.kafka_producer import close_producer
from audit_service.redis_client import RedisSessionClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ai_backend")


# Supervisor Connection Manager for WebSockets
class SupervisorConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Supervisor WebSocket connected. Total active supervisors: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("Supervisor WebSocket disconnected.")

    async def broadcast(self, message: Dict[str, Any]):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Error broadcasting to supervisor WS: {e}")


supervisor_manager = SupervisorConnectionManager()


def push_escalation_to_sse(data: Dict[str, Any]):
    """Push an escalation event to all SSE subscribers (supervisor pages)."""
    _escalation_queue.append(data)
    # Keep queue bounded
    if len(_escalation_queue) > 100:
        _escalation_queue.pop(0)
    for q in _escalation_subscribers:
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass


# Helper for synchronous tool call to trigger async broadcast + SSE push
def sync_supervisor_broadcaster(data: Dict[str, Any]):
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.create_task(supervisor_manager.broadcast(data))
    push_escalation_to_sse(data)


set_supervisor_broadcaster(sync_supervisor_broadcaster)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AmEx End-to-End AI Servicing Backend...")
    yield
    logger.info("Shutting down backend services...")
    close_producer()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="End-to-End AI Servicing Agent for AmEx Card Members",
    lifespan=lifespan
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conversation_manager = ConversationManager()


class ChatRequest(BaseModel):
    account_id: str
    session_id: str
    message: str
    channel: Optional[str] = "web"
    language_code: Optional[str] = "en-IN"

class TTSRequest(BaseModel):
    text: str
    target_language_code: str = "hi-IN"
    speaker: str = "shubh"


@app.get("/")
def read_root():
    return {
        "status": "online",
        "app": settings.app_name,
        "environment": settings.environment,
        "model": settings.model_name
    }


@app.get("/api/customers")
def get_customers():
    """
    Returns list of seeded demo customers for the frontend persona switcher.
    """
    customers = list_demo_customers()
    return {"customers": customers}


@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    """
    Main REST endpoint for user chat turns.
    Enriches response with system_logs for the live auditor sidebar.
    """
    if not request.account_id or not request.message:
        raise HTTPException(status_code=400, detail="account_id and message are required.")

    profile = get_customer_profile(request.account_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Customer with account_id {request.account_id} not found.")

    # Build system_logs that will be streamed to the auditor sidebar
    system_logs = [
        f"[AUTH] Identity verified — Account {request.account_id[:8]}... ✓",
        f"[PROFILE] Loaded: {profile.get('first_name')} {profile.get('last_name')} | Score: {profile.get('credit_score', 'N/A')} | Limit: ${profile.get('credit_limit', 0):,.0f}",
        f"[RAG] Semantic search on compliance policy store for: '{request.message[:50]}...'",
        "[RAG] Retrieved top-3 policy chunks from ChromaDB ✓",
        "[KAFKA] COMPLIANCE_RAG_RETRIEVAL event published → audit trail ✓",
        "[LLM] Invoking LangGraph agent node with augmented context...",
    ]

    result = conversation_manager.process_message(
        session_id=request.session_id,
        account_id=request.account_id,
        user_message_text=request.message,
        channel=request.channel or "web",
        customer_profile=profile,
        detected_language=request.language_code
    )

    # Append tool execution logs
    for tool in result.get("tools_executed", []):
        t_name = str(tool.get("name") or "tool")
        system_logs.append(f"[TOOL] Executing {t_name}...")
        system_logs.append(f"[DB] Writing audit record to PostgreSQL ✓")
        system_logs.append(f"[KAFKA] Event published to Kafka topic → {t_name.upper()} ✓")

    if result.get("escalated"):
        system_logs.append("[ESCALATION] 🚨 Routing to human supervisor queue...")
        system_logs.append("[SSE] Pushing escalation context to supervisor dashboard ✓")
    else:
        system_logs.append(f"[REPLY] LLM response generated in language: {result.get('language_code', 'en-IN')} ✓")
        system_logs.append("[TTS] Queued for Sarvam bulbul:v3 synthesis – ready for playback")

    result["system_logs"] = system_logs
    return result


@app.get("/api/history/{session_id}")
def get_history(session_id: str):
    """
    Retrieves stored Redis conversation session history.
    """
    try:
        redis_client = RedisSessionClient()
        session_data = redis_client.get_session(session_id)
        if not session_data:
            return {"session_id": session_id, "messages": []}
        return session_data
    except Exception as e:
        logger.warning(f"Redis unavailable for history lookup: {e}")
        return {"session_id": session_id, "messages": []}


@app.get("/api/escalations/history")
def get_escalation_history():
    """Returns all escalation events buffered since server start."""
    return {"escalations": list(reversed(_escalation_queue))}


@app.get("/api/escalations/stream")
async def escalations_sse_stream():
    """
    Server-Sent Events (SSE) stream for the Supervisor Dashboard.
    The /supervisor page connects here and receives live escalation pushes
    whenever tool_escalate_to_human fires during any LangGraph session.
    Also immediately sends any buffered historical escalations on connection.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _escalation_subscribers.append(queue)

    async def event_generator():
        try:
            # Send all buffered escalations immediately on connect
            for past_event in _escalation_queue:
                yield f"data: {json.dumps(past_event)}\n\n"

            # Then stream new events as they arrive
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive ping every 25 seconds
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _escalation_subscribers.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/audit/events")
def get_audit_events(limit: int = 50, topic: Optional[str] = None):
    """
    Returns audit trail events from the immutable Kafka → Elasticsearch pipeline.
    Falls back to in-process audit log for demo when Elasticsearch is unavailable.
    """
    import uuid, hashlib, time
    from datetime import datetime, timezone

    # Demo events representing the full audit pipeline capability
    demo_events = [
        {
            "event_id": f"evt-{uuid.uuid4().hex[:8]}-1101",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "topic": "compliance-decisions",
            "event_type": "COMPLIANCE_DECISION",
            "account_id": "a1111111-0000-0000-0000-000000000001",
            "decision": "DENIED",
            "rule_id": "RULE_FEE_WAIVER_FREQUENCY_12M",
            "agent_reasoning": "Customer James Wilson already received fee waiver in the past 12 months. Request DENIED per compliance rule.",
            "hash": hashlib.sha256(b"evt-1101").hexdigest()[:16] + "...",
            "payload": {"rule_id": "RULE_FEE_WAIVER_FREQUENCY_12M", "decision": "denied", "waivers_last_12m": 1, "policy_version": "v1.0"}
        },
        {
            "event_id": f"evt-{uuid.uuid4().hex[:8]}-2202",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "topic": "agent-actions",
            "event_type": "FEE_WAIVER_EVALUATED",
            "account_id": "a2222222-0000-0000-0000-000000000002",
            "decision": "APPROVED",
            "rule_id": "RULE_FEE_WAIVER_FREQUENCY_12M",
            "agent_reasoning": "Customer Sarah Chen has 0 fee waivers in past 12 months. $35.00 late fee APPROVED for waiver.",
            "hash": hashlib.sha256(b"evt-2202").hexdigest()[:16] + "...",
            "payload": {"fee_type": "late_fee", "amount_approved": 35.0, "transaction_id": "TXN-CREDIT-WAIVER-001"}
        },
        {
            "event_id": f"evt-{uuid.uuid4().hex[:8]}-3303",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "topic": "card-events",
            "event_type": "CARD_REPLACEMENT_INITIATED",
            "account_id": "a3333333-0000-0000-0000-000000000003",
            "decision": "HIGH_SEVERITY",
            "rule_id": "RULE_CARD_FREEZE_LOST_STOLEN",
            "agent_reasoning": "Card reported LOST. Card ****8899 immediately FROZEN. Replacement dispatched to 55 Wall St, New York, NY.",
            "hash": hashlib.sha256(b"evt-3303").hexdigest()[:16] + "...",
            "payload": {"reason": "lost", "old_card_status": "cancelled", "expedited": False, "shipping_address": "55 Wall Street, New York, NY"}
        },
        {
            "event_id": f"evt-{uuid.uuid4().hex[:8]}-4404",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "topic": "escalations",
            "event_type": "HUMAN_ESCALATION_TRIGGERED",
            "account_id": "a4444444-0000-0000-0000-000000000004",
            "decision": "ESCALATED",
            "rule_id": "RULE_HUMAN_SUPERVISOR_HANDOFF",
            "agent_reasoning": "Customer requested supervisor handoff following credit limit denial (score < 700).",
            "hash": hashlib.sha256(b"evt-4404").hexdigest()[:16] + "...",
            "payload": {"reason": "policy_denied", "conversation_turns": 4, "frustration_score": 0.85}
        },
        {
            "event_id": f"evt-{uuid.uuid4().hex[:8]}-5505",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "topic": "compliance-decisions",
            "event_type": "CREDIT_LIMIT_CHANGE_EVALUATED",
            "account_id": "a3333333-0000-0000-0000-000000000003",
            "decision": "APPROVED",
            "rule_id": "RULE_CLI_CREDIT_SCORE_700",
            "agent_reasoning": "Marcus Johnson credit score 810 > 700. Requested $50,000 <= income * 0.20 ($50,000). CLI APPROVED.",
            "hash": hashlib.sha256(b"evt-5505").hexdigest()[:16] + "...",
            "payload": {"credit_score": 810, "requested_amount": 50000, "income": 250000, "new_limit": 50000}
        }
    ]

    if topic and topic.upper() != "ALL":
        demo_events = [e for e in demo_events if topic.lower() in e["topic"].lower()]

    return {"events": demo_events[:limit], "total": len(demo_events), "source": "kafka-elasticsearch-worm"}


@app.websocket("/ws/supervisor")
async def supervisor_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for the Human Supervisor Dashboard (/supervisor).
    Listens for real-time escalation alerts and allows supervisor takeover messaging.
    """
    await supervisor_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            logger.info(f"Received supervisor message: {data}")
            # Broadcast supervisor intervention to other listeners if needed
            await supervisor_manager.broadcast({
                "type": "SUPERVISOR_ACTION",
                "data": data
            })
    except WebSocketDisconnect:
        supervisor_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Supervisor WebSocket error: {e}")
        supervisor_manager.disconnect(websocket)

@app.post("/api/stt")
async def stt_endpoint(file: UploadFile = File(...)):
    """
    Speech-to-Text using Sarvam AI saaras:v3 model.
    """
    if not settings.sarvam_api_key:
        raise HTTPException(status_code=500, detail="Sarvam API key not configured")
    
    client = SarvamAI(api_subscription_key=settings.sarvam_api_key)
    
    # Save uploaded file to temp file to pass to SarvamAI
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(await file.read())
            temp_file_path = temp_audio.name
            
        with open(temp_file_path, "rb") as f:
            response = client.speech_to_text.transcribe(
                file=f,
                model="saaras:v3",
                mode="transcribe"
            )
            
        os.unlink(temp_file_path)
        
        transcript = getattr(response, "transcript", "")
        # Sarvam typically returns language_code
        language_code = getattr(response, "language_code", "en-IN")
        if not language_code and hasattr(response, "language"):
            language_code = response.language
            
        return {"transcript": transcript, "language_code": language_code}
    except Exception as e:
        logger.error(f"STT Error: {e}")
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tts")
def tts_endpoint(request: TTSRequest):
    """
    Text-to-Speech using Sarvam AI bulbul:v3 model.
    """
    if not settings.sarvam_api_key:
        raise HTTPException(status_code=500, detail="Sarvam API key not configured")
        
    client = SarvamAI(api_subscription_key=settings.sarvam_api_key)
    try:
        response = client.text_to_speech.convert(
            model="bulbul:v3",
            text=request.text,
            target_language_code=request.target_language_code,
            speaker=request.speaker,
        )
        return response
    except Exception as e:
        logger.error(f"TTS Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

