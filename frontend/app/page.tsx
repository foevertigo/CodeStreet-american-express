"use client";

import { useState, useRef, useEffect } from "react";
import { useMicVAD } from "@ricky0123/vad-react";
import { Activity } from "lucide-react";

interface Message {
  id: string;
  sender: "user" | "bot" | "system";
  text: string;
  tools?: { name: string; content: string }[];
  timestamp: string;
}

function timestamp() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function MinimalistVoiceAgent() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "init",
      sender: "bot",
      text: "Hello. I'm your autonomous servicing agent. How can I help you today?",
      timestamp: timestamp(),
    },
  ]);

  const [isAiThinking, setIsAiThinking] = useState(false);
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);
  const [isUserSpeaking, setIsUserSpeaking] = useState(false);
  const [hasStarted, setHasStarted] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isProcessingRef = useRef(false);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isAiThinking]);

  // Silero VAD — ML model that distinguishes speech from background noise
  const vad = useMicVAD({
    startOnLoad: hasStarted,
    modelURL: "/silero_vad_v5.onnx",
    workletURL: "/vad.worklet.bundle.min.js",
    onSpeechStart: () => {
      if (!isProcessingRef.current && !isAiSpeaking) {
        setIsUserSpeaking(true);
      }
    },
    onSpeechEnd: async (audio: Float32Array) => {
      setIsUserSpeaking(false);

      if (isProcessingRef.current || isAiSpeaking) return;

      isProcessingRef.current = true;
      setIsAiThinking(true);

      try {
        // Convert Float32Array → WAV blob for Sarvam STT
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

        if (transcript && transcript.length > 0) {
          await sendMessage(transcript);
        } else {
          // Short noise / no speech detected
          setIsAiThinking(false);
          isProcessingRef.current = false;
        }
      } catch (e) {
        console.error("STT error", e);
        setIsAiThinking(false);
        isProcessingRef.current = false;
      }
    },
    onVADMisfire: () => {
      setIsUserSpeaking(false);
    },
  });

  const sendMessage = async (text: string) => {
    setMessages((prev) => [
      ...prev,
      { id: Math.random().toString(), sender: "user", text, timestamp: timestamp() },
    ]);

    try {
      const controller = new AbortController();
      const tid = setTimeout(() => controller.abort(), 30000);

      const res = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_id: "a3333333-0000-0000-0000-000000000003",
          session_id: "sess-minimal-001",
          message: text,
          channel: "voice",
        }),
        signal: controller.signal,
      });

      clearTimeout(tid);
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();

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

      await playSarvamTTS(data.reply);
    } catch (err: any) {
      setIsAiThinking(false);
      setMessages((prev) => [
        ...prev,
        {
          id: Math.random().toString(),
          sender: "system",
          text:
            err.name === "AbortError"
              ? "Request timed out evaluating policies."
              : `Backend error: ${err.message}`,
          timestamp: timestamp(),
        },
      ]);
      isProcessingRef.current = false;
    }
  };

  const playSarvamTTS = async (text: string) => {
    setIsAiSpeaking(true);
    try {
      const res = await fetch("http://localhost:8000/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          target_language_code: "en-IN",
          speaker: "shubh",
        }),
      });
      if (!res.ok) throw new Error("TTS failed");
      const data = await res.json();
      if (data?.audios?.length > 0) {
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
      console.error("TTS error", e);
      setIsAiSpeaking(false);
      isProcessingRef.current = false;
    }
  };

  // ----- WAV encoder -----
  function float32ToWav(samples: Float32Array, sampleRate: number): Blob {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const writeStr = (o: number, s: string) => {
      for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i));
    };
    writeStr(0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    writeStr(8, "WAVE");
    writeStr(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, "data");
    view.setUint32(40, samples.length * 2, true);
    let offset = 44;
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      offset += 2;
    }
    return new Blob([buffer], { type: "audio/wav" });
  }

  // ----- Blob state -----
  const blobClass = isUserSpeaking
    ? "blob blob-active"
    : isAiSpeaking || isAiThinking
    ? "blob blob-speaking"
    : "blob";

  const statusLabel = isAiThinking
    ? "Evaluating..."
    : isAiSpeaking
    ? "Agent Speaking"
    : isUserSpeaking
    ? "Listening"
    : hasStarted
    ? "Ready"
    : "Idle";

  // ----- Splash screen -----
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
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-[#f4f4f0] text-[#1a1a1a]">
      {/* ───── Left — Blob ───── */}
      <div className="flex w-1/2 flex-col items-center justify-center">
        <div className="relative flex h-[480px] w-[480px] items-center justify-center">
          <div className={`h-[240px] w-[240px] ${blobClass}`} />
          <p className="absolute bottom-8 text-xs font-bold uppercase tracking-widest opacity-40">
            {statusLabel}
          </p>
        </div>
      </div>

      {/* ───── Right — Chat ───── */}
      <div className="relative flex h-full w-1/2 flex-col border-l border-[#e0e0dc] bg-white">
        <div className="flex-1 space-y-8 overflow-y-auto px-12 py-12 pb-36">
          {messages.map((m) => (
            <div key={m.id} className="duration-500 animate-in fade-in slide-in-from-bottom-2">
              {m.sender === "user" ? (
                <p className="text-right font-serif text-2xl leading-tight text-[#1a1a1a]">
                  "{m.text}"
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
                        <Activity className="h-3 w-3" /> Actions
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
              <div className="h-2 w-2 animate-ping rounded-full bg-emerald-500" />
              <span className="text-xs font-bold uppercase tracking-widest text-emerald-600">
                Evaluating policies...
              </span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Optional text input */}
        <div className="absolute bottom-0 w-full bg-gradient-to-t from-white via-white to-transparent pb-8 pt-12 px-12">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const el = (e.target as HTMLFormElement).elements.namedItem("chatInput") as HTMLInputElement;
              if (el.value.trim()) {
                isProcessingRef.current = true;
                setIsAiThinking(true);
                sendMessage(el.value.trim());
                el.value = "";
              }
            }}
          >
            <input
              name="chatInput"
              type="text"
              placeholder="Or type here..."
              className="w-full rounded-full border border-[#e0e0dc] bg-[#f8f8f6] px-6 py-4 text-sm text-[#1a1a1a] placeholder-[#bbb] shadow-sm transition-all focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
          </form>
        </div>
      </div>
    </div>
  );
}
