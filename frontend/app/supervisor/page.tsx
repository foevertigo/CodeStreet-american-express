"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";

interface EscalationEvent {
  id: string;
  type: string;
  session_id: string;
  account_id: string;
  customer_name: string;
  reason: string;
  summary: string;
  timestamp: string;
  status: "pending" | "claimed" | "resolved";
}

function timeAgo(ts: string) {
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export default function SupervisorDashboard() {
  const [escalations, setEscalations] = useState<EscalationEvent[]>([]);
  const [selected, setSelected] = useState<EscalationEvent | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [claimedIds, setClaimedIds] = useState<Set<string>>(new Set());
  const [resolvedIds, setResolvedIds] = useState<Set<string>>(new Set());
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    // Connect to SSE stream for live escalations
    const connectSSE = () => {
      const es = new EventSource("http://localhost:8000/api/escalations/stream");
      eventSourceRef.current = es;

      es.onopen = () => setIsConnected(true);
      es.onerror = () => {
        setIsConnected(false);
        // Reconnect after 3s
        setTimeout(connectSSE, 3000);
      };

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (!data.type) return;

          const event: EscalationEvent = {
            id: `${data.session_id}-${Date.now()}`,
            type: data.type,
            session_id: data.session_id || "unknown",
            account_id: data.account_id || "unknown",
            customer_name: data.customer_name || "Unknown Customer",
            reason: data.reason || "Escalation requested",
            summary: data.summary || "Customer has requested human agent assistance.",
            timestamp: data.timestamp || new Date().toISOString(),
            status: "pending",
          };

          setEscalations((prev) => {
            const exists = prev.some((e) => e.session_id === event.session_id);
            if (exists) return prev;
            return [event, ...prev];
          });
        } catch (_) {}
      };
    };

    // Also load historical escalations
    fetch("http://localhost:8000/api/escalations/history")
      .then((r) => r.json())
      .then((data) => {
        const historical = (data.escalations || []).map((ev: any, i: number) => ({
          id: `hist-${i}`,
          type: ev.type || "ESCALATION_ALERT",
          session_id: ev.session_id || "unknown",
          account_id: ev.account_id || "unknown",
          customer_name: ev.customer_name || "Card Member",
          reason: ev.reason || "Escalation",
          summary: ev.summary || "Requires human attention.",
          timestamp: ev.timestamp || new Date().toISOString(),
          status: "pending" as const,
        }));
        if (historical.length > 0) setEscalations(historical);
      })
      .catch(() => {});

    connectSSE();

    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  const claim = (id: string) => setClaimedIds((prev) => new Set(prev).add(id));
  const resolve = (id: string) => {
    setResolvedIds((prev) => new Set(prev).add(id));
    if (selected?.id === id) setSelected(null);
  };

  const pendingCount = escalations.filter(
    (e) => !resolvedIds.has(e.id)
  ).length;

  return (
    <div className="flex h-screen overflow-hidden bg-[#0f0f0f] text-white font-mono">
      {/* ── Sidebar: Queue ── */}
      <div className="flex w-[380px] flex-col border-r border-white/10">
        {/* Header */}
        <div className="border-b border-white/10 px-6 py-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[10px] uppercase tracking-widest text-white/30">AmEx</p>
              <h1 className="text-lg font-bold tracking-tight">Supervisor Console</h1>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full ${isConnected ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`}
              />
              <span className="text-[10px] text-white/40">
                {isConnected ? "LIVE" : "OFFLINE"}
              </span>
            </div>
          </div>
          <div className="mt-4 flex gap-3">
            <div className="flex-1 rounded-lg bg-white/5 px-3 py-2 text-center">
              <p className="text-2xl font-bold text-amber-400">{pendingCount}</p>
              <p className="text-[9px] uppercase tracking-widest text-white/30">Pending</p>
            </div>
            <div className="flex-1 rounded-lg bg-white/5 px-3 py-2 text-center">
              <p className="text-2xl font-bold text-emerald-400">{resolvedIds.size}</p>
              <p className="text-[9px] uppercase tracking-widest text-white/30">Resolved</p>
            </div>
            <div className="flex-1 rounded-lg bg-white/5 px-3 py-2 text-center">
              <p className="text-2xl font-bold text-blue-400">{escalations.length}</p>
              <p className="text-[9px] uppercase tracking-widest text-white/30">Total</p>
            </div>
          </div>
        </div>

        {/* Escalation List */}
        <div className="flex-1 overflow-y-auto">
          {escalations.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 opacity-30">
              <div className="text-4xl">⚡</div>
              <p className="text-xs tracking-widest uppercase">No escalations yet</p>
              <p className="text-[10px] text-center px-6">
                When an AI agent transfers a session, it will appear here instantly.
              </p>
            </div>
          ) : (
            escalations.map((ev) => {
              const isResolved = resolvedIds.has(ev.id);
              const isClaimed = claimedIds.has(ev.id);
              const isActive = selected?.id === ev.id;

              return (
                <button
                  key={ev.id}
                  onClick={() => !isResolved && setSelected(ev)}
                  disabled={isResolved}
                  className={`w-full border-b border-white/5 px-5 py-4 text-left transition-all hover:bg-white/5 
                    ${isActive ? "bg-white/10 border-l-2 border-l-amber-400" : ""}
                    ${isResolved ? "opacity-30 cursor-default" : "cursor-pointer"}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        {!isResolved && !isClaimed && (
                          <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse flex-shrink-0 mt-1" />
                        )}
                        <p className="font-bold text-sm truncate">{ev.customer_name}</p>
                      </div>
                      <p className="text-[10px] text-white/40 truncate">{ev.reason}</p>
                      <p className="text-[10px] text-white/25 mt-1">{timeAgo(ev.timestamp)}</p>
                    </div>
                    <span
                      className={`text-[9px] px-2 py-0.5 rounded-full flex-shrink-0 uppercase tracking-wider font-bold
                        ${isResolved ? "bg-white/10 text-white/30" : isClaimed ? "bg-blue-500/20 text-blue-400" : "bg-red-500/20 text-red-400"}`}
                    >
                      {isResolved ? "DONE" : isClaimed ? "ACTIVE" : "NEW"}
                    </span>
                  </div>
                </button>
              );
            })
          )}
        </div>

        <div className="border-t border-white/10 px-5 py-3">
          <Link
            href="/"
            className="block text-center text-[10px] uppercase tracking-widest text-white/30 hover:text-white/60 transition-colors"
          >
            ← Back to Agent View
          </Link>
        </div>
      </div>

      {/* ── Main: Case Detail ── */}
      <div className="flex-1 flex flex-col">
        {!selected ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 opacity-20">
            <div className="text-6xl">🎛️</div>
            <p className="text-sm uppercase tracking-widest">Select an escalation to review</p>
          </div>
        ) : (
          <div className="flex flex-col h-full">
            {/* Case header */}
            <div className="border-b border-white/10 px-8 py-6">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-amber-400 mb-1">
                    🚨 Active Escalation
                  </p>
                  <h2 className="text-2xl font-bold">{selected.customer_name}</h2>
                  <p className="text-sm text-white/40 mt-0.5">
                    Account: {selected.account_id} · Session: {selected.session_id}
                  </p>
                </div>
                <div className="flex gap-3">
                  {!claimedIds.has(selected.id) && (
                    <button
                      onClick={() => claim(selected.id)}
                      className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-bold hover:bg-blue-500 transition-colors"
                    >
                      Take Over Chat
                    </button>
                  )}
                  <button
                    onClick={() => resolve(selected.id)}
                    className="rounded-lg bg-emerald-700 px-5 py-2.5 text-sm font-bold hover:bg-emerald-600 transition-colors"
                  >
                    Mark Resolved
                  </button>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-8 py-6 space-y-6">
              {/* AI Handoff Summary */}
              <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-5">
                <p className="text-[10px] uppercase tracking-widest text-amber-400 mb-3 flex items-center gap-2">
                  <span>🤖</span> AI-Generated Handoff Summary
                </p>
                <p className="text-white/80 leading-relaxed">{selected.summary}</p>
              </div>

              {/* Case metadata */}
              <div className="grid grid-cols-2 gap-4">
                {[
                  { label: "Escalation Reason", value: selected.reason },
                  { label: "Session ID", value: selected.session_id },
                  { label: "Account ID", value: selected.account_id },
                  { label: "Time", value: new Date(selected.timestamp).toLocaleString() },
                ].map(({ label, value }) => (
                  <div key={label} className="rounded-lg bg-white/5 p-4">
                    <p className="text-[9px] uppercase tracking-widest text-white/30 mb-1">{label}</p>
                    <p className="text-sm font-medium break-all">{value}</p>
                  </div>
                ))}
              </div>

              {/* Action taken indicator */}
              {claimedIds.has(selected.id) && (
                <div className="rounded-xl border border-blue-500/30 bg-blue-500/5 p-5">
                  <p className="text-blue-400 font-bold mb-1">✅ Chat session claimed by you</p>
                  <p className="text-white/50 text-sm">
                    You have taken ownership of this session. 
                    The AI agent has been paused and the customer is now waiting for your response.
                  </p>
                </div>
              )}

              {/* Recommended actions */}
              <div>
                <p className="text-[10px] uppercase tracking-widest text-white/30 mb-3">
                  Recommended Actions
                </p>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    "Override Fee Waiver",
                    "Manual Credit Review",
                    "Fraud Investigation",
                    "Account Freeze",
                    "Executive Escalation",
                    "Request Documents",
                  ].map((action) => (
                    <button
                      key={action}
                      className="rounded-lg border border-white/10 bg-white/5 px-3 py-3 text-xs text-white/60 hover:bg-white/10 hover:text-white transition-all text-left"
                    >
                      {action}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
