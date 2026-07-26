"use client";

import { useState, useRef, useEffect } from "react";
import { useMicVAD } from "@ricky0123/vad-react";
import { Activity, Terminal, ExternalLink, User, ShieldCheck, Square, RotateCcw } from "lucide-react";
import Link from "next/link";

interface Message {
  id: string;
  sender: "user" | "bot" | "system";
  text: string;
  tools?: { name: string; content: string }[];
  timestamp: string;
}

interface AuditLog {
  id: string;
  text: string;
  ts: string;
  type: "auth" | "rag" | "kafka" | "tool" | "llm" | "tts" | "escalation" | "db" | "info";
}

function timestamp() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function logTs() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

const LOG_TYPE_STYLE: Record<AuditLog["type"], string> = {
  auth: "text-emerald-400",
  rag: "text-blue-400",
  kafka: "text-purple-400",
  tool: "text-amber-400",
  llm: "text-cyan-400",
  tts: "text-pink-400",
  escalation: "text-red-400",
  db: "text-indigo-400",
  info: "text-white/40",
};

function parseLogType(text: string): AuditLog["type"] {
  if (text.includes("[AUTH]")) return "auth";
  if (text.includes("[RAG]")) return "rag";
  if (text.includes("[KAFKA]")) return "kafka";
  if (text.includes("[TOOL]")) return "tool";
  if (text.includes("[LLM]")) return "llm";
  if (text.includes("[TTS]")) return "tts";
  if (text.includes("[ESCALATION]")) return "escalation";
  if (text.includes("[DB]")) return "db";
  return "info";
}

// LATENCY MASKING: Filler messages that play while the backend processes
const THINKING_FILLERS = [
  "Authenticating your identity securely...",
  "Retrieving your account profile...",
  "Scanning compliance policy database...",
  "Evaluating your request against regulations...",
  "Processing with AI agent...",
];

export default function MinimalistVoiceAgent() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "init",
      sender: "bot",
      text: "Hello. I'm your autonomous servicing agent. How can I help you today?",
      timestamp: "just now",
    },
  ]);

  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([
    { id: "boot", text: "[SYS] Compliance Policy Engine initialized ✓", ts: "--:--", type: "info" },
    { id: "boot2", text: "[RAG] ChromaDB loaded — 9 compliance rules indexed", ts: "--:--", type: "rag" },
    { id: "boot3", text: "[SYS] Sarvam AI STT/TTS ready", ts: "--:--", type: "info" },
  ]);

  const [isAiThinking, setIsAiThinking] = useState(false);
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);
  const [isUserSpeaking, setIsUserSpeaking] = useState(false);
  const [hasStarted, setHasStarted] = useState(false);
  const [fillerText, setFillerText] = useState("");
  const [fillerIdx, setFillerIdx] = useState(0);
  const [showAudit, setShowAudit] = useState(true);
  const [selectedAccountId, setSelectedAccountId] = useState("a2222222-0000-0000-0000-000000000002");
  const [sessionId, setSessionId] = useState(() => "sess-" + Math.random().toString(36).substring(2, 9));
  const [customers, setCustomers] = useState<any[]>([]);

  useEffect(() => {
    fetch("http://localhost:8000/api/customers")
      .then((res) => res.json())
      .then((data) => {
        if (data.customers && data.customers.length > 0) {
          setCustomers(data.customers);
        }
      })
      .catch((err) => console.error("Failed to load customer profiles:", err));
  }, []);

  const resetChat = (newProfileName?: string) => {
    const newSess = "sess-" + Math.random().toString(36).substring(2, 9);
    setSessionId(newSess);
    setMessages([
      {
        id: "init-" + Date.now(),
        sender: "bot",
        text: newProfileName
          ? `Switched profile to ${newProfileName}. Started fresh chat session.`
          : "Chat session ended. Ready for a new conversation.",
        timestamp: timestamp(),
      },
    ]);
    setIsAiThinking(false);
    setIsAiSpeaking(false);
    isProcessingRef.current = false;
    stopFiller();
    addAuditLog(`[SYS] Chat session reset. New session initialized (${newSess.slice(0, 10)}) ✓`);
  };

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const auditEndRef = useRef<HTMLDivElement>(null);
  const isProcessingRef = useRef(false);
  const fillerIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    auditEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [auditLogs]);

  const addAuditLog = (text: string) => {
    setAuditLogs((prev) => [
      ...prev,
      { id: Math.random().toString(), text, ts: logTs(), type: parseLogType(text) },
    ]);
  };

  const startFiller = () => {
    let idx = 0;
    setFillerText(THINKING_FILLERS[0]);
    fillerIntervalRef.current = setInterval(() => {
      idx = (idx + 1) % THINKING_FILLERS.length;
      setFillerText(THINKING_FILLERS[idx]);
    }, 1600);
  };

  const stopFiller = () => {
    if (fillerIntervalRef.current) {
      clearInterval(fillerIntervalRef.current);
      fillerIntervalRef.current = null;
    }
    setFillerText("");
  };

  // Silero VAD — ML model that distinguishes speech from background noise.
  // IMPORTANT: The library builds its own URL: baseAssetPath + "silero_vad_v5.onnx"
  // We must point baseAssetPath to "/" so it loads from Next.js /public/.
  const vad = useMicVAD({
    startOnLoad: hasStarted,
    model: "v5",
    onnxWASMBasePath: "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.27.0/dist/",
    baseAssetPath: "https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.30/dist/",
    ortConfig: (ort: any) => {
      ort.env.wasm.numThreads = 1;
    },
    positiveSpeechThreshold: 0.6,
    negativeSpeechThreshold: 0.35,
    onSpeechStart: () => {



      if (!isProcessingRef.current && !isAiSpeaking) {
        setIsUserSpeaking(true);
        addAuditLog("[MIC] Voice activity detected — speech captured");
      }
    },
    onSpeechEnd: async (audio: Float32Array) => {
      setIsUserSpeaking(false);
      if (isProcessingRef.current || isAiSpeaking) return;

      isProcessingRef.current = true;
      setIsAiThinking(true);
      startFiller();
      addAuditLog("[STT] Sending audio to Sarvam saaras:v3...");

      try {
        const wavBlob = float32ToWav(audio, 16000);
        const formData = new FormData();
        formData.append("file", wavBlob, "speech.wav");

        const sttRes = await fetch("http://localhost:8000/api/stt", {
          method: "POST",
          body: formData,
        });

        if (!sttRes.ok) throw new Error(`STT failed: ${sttRes.status}`);
        const sttData = await sttRes.json();
        const transcript = sttData.transcript?.trim();
        const langCode = sttData.language_code || "en-IN";

        if (transcript && transcript.length > 0) {
          addAuditLog(`[STT] Transcript: "${transcript.slice(0, 60)}" | Lang: ${langCode} ✓`);
          await sendMessage(transcript, langCode);
        } else {
          addAuditLog("[STT] No speech detected — discarding audio");
          stopFiller();
          setIsAiThinking(false);
          isProcessingRef.current = false;
        }
      } catch (e) {
        console.error("STT error", e);
        addAuditLog(`[ERROR] STT failed: ${String(e)}`);
        stopFiller();
        setIsAiThinking(false);
        isProcessingRef.current = false;
      }
    },
    onVADMisfire: () => {
      setIsUserSpeaking(false);
    },
  });

  const sendMessage = async (text: string, langCode: string = "en-IN") => {
    setMessages((prev) => [
      ...prev,
      { id: Math.random().toString(), sender: "user", text, timestamp: timestamp() },
    ]);

    try {
      const controller = new AbortController();
      const tid = setTimeout(() => controller.abort(), 45000);

      const res = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_id: selectedAccountId,
          session_id: sessionId,
          message: text,
          channel: "voice",
          language_code: langCode,
        }),
        signal: controller.signal,
      });

      clearTimeout(tid);
      stopFiller();

      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();

      // Animate system_logs into the audit sidebar sequentially
      const logs: string[] = data.system_logs || [];
      logs.forEach((log, i) => {
        setTimeout(() => addAuditLog(log), i * 120);
      });

      setMessages((prev) => [
        ...prev,
        {
          id: Math.random().toString(),
          sender: "bot",
          text: data.reply || "Your request has been processed.",
          tools: data.tools_executed,
          timestamp: timestamp(),
        },
      ]);
      setIsAiThinking(false);

      await playSarvamTTS(data.reply, data.language_code || langCode);
    } catch (err: any) {
      stopFiller();
      setIsAiThinking(false);
      const msg = err.name === "AbortError"
        ? "Request timed out — please try again."
        : `Error: ${err.message}`;
      addAuditLog(`[ERROR] ${msg}`);
      setMessages((prev) => [
        ...prev,
        { id: Math.random().toString(), sender: "system", text: msg, timestamp: timestamp() },
      ]);
      isProcessingRef.current = false;
    }
  };

  const playSarvamTTS = async (text: string, langCode: string = "en-IN") => {
    setIsAiSpeaking(true);
    addAuditLog(`[TTS] Sarvam bulbul:v3 synthesizing in ${langCode}...`);
    try {
      const res = await fetch("http://localhost:8000/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, target_language_code: langCode, speaker: "shubh" }),
      });
      if (!res.ok) throw new Error("TTS failed");
      const data = await res.json();
      if (data?.audios?.length > 0) {
        addAuditLog("[TTS] Audio ready — playing response ✓");
        const audio = new Audio("data:audio/wav;base64," + data.audios[0]);
        audio.onended = () => {
          setIsAiSpeaking(false);
          isProcessingRef.current = false;
        };
        await audio.play();
      } else {
        throw new Error("No audio payload");
      }
    } catch (e) {
      addAuditLog(`[ERROR] TTS: ${String(e)}`);
      setIsAiSpeaking(false);
      isProcessingRef.current = false;
    }
  };

  // WAV encoder
  function float32ToWav(samples: Float32Array, sampleRate: number): Blob {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); };
    w(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true);
    w(8, "WAVE"); w(12, "fmt ");
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    w(36, "data"); view.setUint32(40, samples.length * 2, true);
    let offset = 44;
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      offset += 2;
    }
    return new Blob([buffer], { type: "audio/wav" });
  }

  // Automatically pause microphone while AI is speaking
  useEffect(() => {
    if (isAiSpeaking && vad.listening) {
      // AI is talking — stop listening to avoid feedback loops
      vad.pause();
    } else if (!isAiSpeaking && hasStarted && !vad.listening && !vad.loading && !vad.errored) {
      // AI finished talking — resume listening
      vad.start();
    }
  }, [isAiSpeaking, hasStarted, vad]);

  const blobClass = isUserSpeaking
    ? "blob blob-active"
    : isAiSpeaking || isAiThinking
    ? "blob blob-speaking"
    : "blob";

  const statusLabel = isAiThinking
    ? "Evaluating"
    : isAiSpeaking
    ? "Speaking"
    : isUserSpeaking
    ? "Listening"
    : hasStarted
    ? "Ready"
    : "Idle";

  // SPLASH SCREEN
  if (!hasStarted) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-[#f4f4f0] text-[#1a1a1a]">
        <p className="mb-2 text-xs uppercase tracking-widest opacity-40">AmEx Autonomous Servicing</p>
        <h1 className="mb-10 font-serif text-5xl font-bold tracking-tight">AI Agent</h1>
        <button
          onClick={() => setHasStarted(true)}
          className="rounded-full border-2 border-[#1a1a1a] px-10 py-4 text-xl font-serif transition-all hover:bg-[#1a1a1a] hover:text-[#f4f4f0]"
        >
          Tap to begin
        </button>
        <Link
          href="/supervisor"
          className="mt-6 text-xs text-[#1a1a1a]/30 hover:text-[#1a1a1a]/60 transition-colors flex items-center gap-1"
        >
          <ExternalLink className="h-3 w-3" /> Supervisor Dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-[#f4f4f0] text-[#1a1a1a]">
      {/* ── LEFT: Blob ── */}
      <div className="flex w-[38%] flex-col items-center justify-center relative flex-shrink-0">
        <div className="relative flex h-[420px] w-[420px] items-center justify-center">
          <div className={`h-[220px] w-[220px] ${blobClass}`} />

          {/* Status label + filler */}
          <div className="absolute bottom-4 left-0 right-0 text-center">
            <p className="text-[10px] font-bold uppercase tracking-widest opacity-40">{statusLabel}</p>
            {fillerText && (
              <p className="mt-1 text-xs text-blue-600/70 animate-pulse px-4">{fillerText}</p>
            )}
          </div>
        </div>

        {/* Supervisor link */}
        <Link
          href="/supervisor"
          className="absolute bottom-5 right-5 flex items-center gap-1 text-[10px] uppercase tracking-widest opacity-20 hover:opacity-60 transition-opacity"
        >
          <ExternalLink className="h-3 w-3" /> Supervisor
        </Link>

        {/* Audit toggle */}
        <button
          onClick={() => setShowAudit((s) => !s)}
          className="absolute bottom-5 left-5 flex items-center gap-1 text-[10px] uppercase tracking-widest opacity-20 hover:opacity-60 transition-opacity"
        >
          <Terminal className="h-3 w-3" /> {showAudit ? "Hide" : "Show"} Logs
        </button>
      </div>

      {/* ── CENTRE: Chat ── */}
      <div
        className={`relative flex flex-col border-x border-[#e0e0dc] bg-white transition-all ${showAudit ? "flex-1" : "flex-1"}`}
      >
        {/* Profile Selector & End Chat Header */}
        <div className="flex items-center justify-between border-b border-[#e0e0dc] px-8 py-3 bg-[#fafaf8]">
          <div className="flex items-center gap-2 text-xs font-semibold text-[#444]">
            <User className="h-4 w-4 text-blue-600" />
            <span>Active Test Profile:</span>
          </div>

          <div className="flex items-center gap-3">
            <select
              value={selectedAccountId}
              onChange={(e) => {
                const newId = e.target.value;
                setSelectedAccountId(newId);
                const cust = customers.find((c) => c.account_id === newId);
                const name = cust ? `${cust.first_name} ${cust.last_name}` : newId.slice(0, 8);
                resetChat(name);
              }}
              className="rounded-md border border-[#ccc] bg-white px-3 py-1.5 text-xs font-medium text-[#1a1a1a] shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
            >
              {customers.length > 0 ? (
                customers.map((c) => (
                  <option key={c.account_id} value={c.account_id}>
                    {c.first_name} {c.last_name} — Score: {c.credit_score} | Limit: ${Number(c.credit_limit).toLocaleString()} ({c.account_status})
                  </option>
                ))
              ) : (
                <>
                  <option value="a6666666-0000-0000-0000-000000000006">Alex Taylor (Score: 720 — Limit $1,400 / Spend $3,000)</option>
                  <option value="a2222222-0000-0000-0000-000000000002">Sarah Chen (Score: 620 — Fee Waiver Eligible)</option>
                  <option value="a1111111-0000-0000-0000-000000000001">James Wilson (Score: 750 — Waiver Ineligible)</option>
                  <option value="a3333333-0000-0000-0000-000000000003">Marcus Johnson (Score: 810 — Fully Eligible)</option>
                  <option value="a4444444-0000-0000-0000-000000000004">Emily Rodriguez (Score: 580 — New Account)</option>
                  <option value="a5555555-0000-0000-0000-000000000005">David Kim (Score: 490 — Suspended Account)</option>
                </>
              )}
            </select>

            <button
              onClick={() => resetChat()}
              className="flex items-center gap-1.5 rounded-md border border-red-200 bg-red-50 hover:bg-red-100 px-3 py-1.5 text-xs font-semibold text-red-600 transition-colors shadow-sm cursor-pointer"
              title="End current session and start a fresh chat"
            >
              <Square className="h-3 w-3 fill-red-600" />
              End Chat
            </button>
          </div>
        </div>

        <div className="flex-1 space-y-8 overflow-y-auto px-10 py-10 pb-36">
          {messages.map((m) => (
            <div key={m.id} className="duration-500 animate-in fade-in slide-in-from-bottom-2">
              {m.sender === "user" ? (
                <p className="text-right font-serif text-2xl leading-tight text-[#1a1a1a]">
                  &ldquo;{m.text}&rdquo;
                </p>
              ) : m.sender === "system" ? (
                <div className="rounded-lg bg-red-50 p-4">
                  <p className="text-sm font-medium text-red-600">{m.text}</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full bg-blue-600" />
                    <span className="text-xs font-bold uppercase tracking-widest text-blue-600">Agent</span>
                    <span className="text-xs opacity-30">{m.timestamp}</span>
                  </div>
                  <p className="text-lg leading-relaxed text-[#333]">{m.text}</p>
                  {m.tools && m.tools.length > 0 && (
                    <div className="mt-3 border-t border-[#f0f0f0] pt-3">
                      <p className="mb-2 flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-[#999]">
                        <Activity className="h-3 w-3" /> Actions Executed
                      </p>
                      <div className="space-y-1">
                        {m.tools.map((t, i) => (
                          <div key={i} className="rounded bg-[#f6f6f4] px-3 py-2 font-mono text-xs text-[#555]">
                            <span className="mb-0.5 block font-bold text-[#1a1a1a]">{t.name}</span>
                            {t.content}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {isAiThinking && (
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 animate-ping rounded-full bg-blue-500" />
              <span className="text-xs font-bold uppercase tracking-widest text-blue-600">
                {fillerText || "Processing..."}
              </span>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Text input */}
        <div className="absolute bottom-0 w-full bg-gradient-to-t from-white via-white to-transparent pb-8 pt-12 px-10">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const el = (e.target as HTMLFormElement).elements.namedItem("chatInput") as HTMLInputElement;
              if (el.value.trim() && !isProcessingRef.current) {
                isProcessingRef.current = true;
                setIsAiThinking(true);
                startFiller();
                sendMessage(el.value.trim());
                el.value = "";
              }
            }}
          >
            <input
              name="chatInput"
              type="text"
              placeholder="Or type here..."
              disabled={isProcessingRef.current}
              className="w-full rounded-full border border-[#e0e0dc] bg-[#f8f8f6] px-6 py-4 text-sm text-[#1a1a1a] placeholder-[#bbb] shadow-sm transition-all focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:opacity-50"
            />
          </form>
        </div>
      </div>

      {/* ── RIGHT: Live Auditor Terminal ── */}
      {showAudit && (
        <div className="flex w-[320px] flex-col bg-[#0b0b0b] font-mono text-xs flex-shrink-0">
          <div className="border-b border-white/10 px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Terminal className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-white/50 uppercase tracking-widest text-[10px]">Audit Log</span>
            </div>
            <div className="flex gap-1">
              <div className="h-2.5 w-2.5 rounded-full bg-red-500/60" />
              <div className="h-2.5 w-2.5 rounded-full bg-amber-500/60" />
              <div className="h-2.5 w-2.5 rounded-full bg-emerald-500/60" />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-1.5">
            {auditLogs.map((log) => (
              <div
                key={log.id}
                className="flex gap-2 animate-in fade-in duration-300 leading-snug"
              >
                <span className="text-white/20 text-[9px] flex-shrink-0 pt-[1px]">{log.ts}</span>
                <span className={`${LOG_TYPE_STYLE[log.type]} break-all`}>{log.text}</span>
              </div>
            ))}
            <div ref={auditEndRef} />
          </div>

          {/* Kafka indicator bar */}
          <div className="border-t border-white/10 px-4 py-2 flex items-center gap-2">
            <div className={`h-1.5 w-1.5 rounded-full ${isAiThinking ? "bg-amber-400 animate-pulse" : "bg-emerald-500"}`} />
            <span className="text-[9px] text-white/30 uppercase tracking-widest">
              {isAiThinking ? "Pipeline active" : `${auditLogs.length} events logged`}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
