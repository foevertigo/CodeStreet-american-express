"use client";

import { useState, useEffect, useRef } from "react";
import {
  UserCheck,
  AlertTriangle,
  Send,
  CheckCircle2,
  Clock,
  MessageSquare,
  Sparkles,
  Activity,
  ArrowRight,
  ShieldCheck,
  User
} from "lucide-react";

interface EscalationAlert {
  session_id: string;
  account_id: string;
  customer_name: string;
  reason: string;
  summary: string;
  timestamp: string;
}

export default function SupervisorDashboard() {
  const [alerts, setAlerts] = useState<EscalationAlert[]>([
    {
      session_id: "sess-historical-002",
      account_id: "a2222222-0000-0000-0000-000000000002",
      customer_name: "Sarah Chen",
      reason: "Policy Denied (Credit Limit Increase)",
      summary: "Customer requested limit increase to $15,000 but credit score is 620 (< 700 policy rule). Customer requested human supervisor review.",
      timestamp: new Date().toLocaleTimeString()
    }
  ]);

  const [selectedAlert, setSelectedAlert] = useState<EscalationAlert | null>(alerts[0]);
  const [sessionMessages, setSessionMessages] = useState<any[]>([]);
  const [supervisorReply, setSupervisorReply] = useState("");
  const [takenOver, setTakenOver] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);

  // Connect WebSocket to /ws/supervisor
  useEffect(() => {
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket("ws://localhost:8000/ws/supervisor");

      ws.onopen = () => {
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "ESCALATION_ALERT") {
            const newAlert: EscalationAlert = {
              session_id: data.session_id,
              account_id: data.account_id,
              customer_name: data.customer_name || "Card Member",
              reason: data.reason || "Human Escalation Triggered",
              summary: data.summary || "Customer requested human supervisor context handoff.",
              timestamp: new Date(data.timestamp || Date.now()).toLocaleTimeString()
            };
            setAlerts((prev) => [newAlert, ...prev]);
            setSelectedAlert(newAlert);
          }
        } catch (e) {
          console.error("Error parsing supervisor WS message:", e);
        }
      };

      ws.onclose = () => setWsConnected(false);
    } catch (e) {
      console.error(e);
    }

    return () => {
      ws?.close();
    };
  }, []);

  // Fetch conversation history when selecting an escalation alert
  useEffect(() => {
    if (!selectedAlert) return;
    fetch(`http://localhost:8000/api/history/${selectedAlert.session_id}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.messages && data.messages.length > 0) {
          setSessionMessages(data.messages);
        } else {
          setSessionMessages([
            { role: "user", content: "I would like to speak to a supervisor manager regarding my credit limit request." },
            { role: "assistant", content: "I have escalated your session to our Human Supervisor Queue along with your account summary." }
          ]);
        }
      })
      .catch(() => {
        setSessionMessages([
          { role: "user", content: "I am frustrated with the automated fee waiver decision. I want a human agent." },
          { role: "assistant", content: "HUMAN ESCALATION TRIGGERED: Session transferred to supervisor queue." }
        ]);
      });
  }, [selectedAlert]);

  const handleTakeOver = () => {
    setTakenOver(true);
    setSessionMessages((prev) => [
      ...prev,
      {
        role: "supervisor",
        content: `[SUPERVISOR INTERVENTION] Hello ${selectedAlert?.customer_name || "Card Member"}, my name is Alex from AmEx Senior Servicing Management. I am taking over this chat with full context of your request.`
      }
    ]);
  };

  const sendSupervisorMessage = () => {
    if (!supervisorReply.trim()) return;
    setSessionMessages((prev) => [
      ...prev,
      { role: "supervisor", content: supervisorReply }
    ]);
    setSupervisorReply("");
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold text-white flex items-center gap-2">
              <UserCheck className="w-6 h-6 text-purple-400" /> Human-in-the-Loop Supervisor Command Center
            </h1>
            <span
              className={`text-xs px-2.5 py-0.5 rounded-full font-mono flex items-center gap-1.5 ${
                wsConnected
                  ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                  : "bg-amber-950 text-amber-400 border border-amber-800"
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${wsConnected ? "bg-emerald-400 animate-pulse" : "bg-amber-400"}`}></span>
              {wsConnected ? "WebSocket Live Listener" : "Connecting WS..."}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Real-time session escalation queue with AI context snapshot & live takeover controls
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* ESCALATION QUEUE (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          <div className="glass-panel p-4 rounded-2xl border border-slate-800">
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-3 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-purple-400" /> Active Escalation Alerts ({alerts.length})
            </h2>

            <div className="space-y-3">
              {alerts.map((alert) => {
                const isSelected = selectedAlert?.session_id === alert.session_id;
                return (
                  <div
                    key={alert.session_id}
                    onClick={() => setSelectedAlert(alert)}
                    className={`p-4 rounded-xl border transition-all cursor-pointer space-y-2 ${
                      isSelected
                        ? "bg-purple-950/40 border-purple-600 shadow-md glow-rose"
                        : "bg-slate-900/80 border-slate-800 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white text-sm">{alert.customer_name}</span>
                      <span className="text-[10px] text-slate-400 font-mono flex items-center gap-1">
                        <Clock className="w-3 h-3" /> {alert.timestamp}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="bg-rose-950 text-rose-300 text-[10px] px-2 py-0.5 rounded font-mono border border-rose-800">
                        {alert.reason}
                      </span>
                    </div>

                    <p className="text-xs text-slate-300 line-clamp-2">{alert.summary}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* CONVERSATION REPLAY & TAKEOVER CONSOLE (7 cols) */}
        <div className="lg:col-span-7 flex flex-col h-[600px] glass-panel rounded-2xl border border-slate-800 p-5">
          {selectedAlert ? (
            <>
              {/* Context Summary Header */}
              <div className="pb-4 mb-4 border-b border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-bold text-lg text-white">{selectedAlert.customer_name}</h3>
                    <p className="text-xs text-slate-400 font-mono">
                      Session ID: {selectedAlert.session_id} | Account: {selectedAlert.account_id}
                    </p>
                  </div>

                  {!takenOver ? (
                    <button
                      onClick={handleTakeOver}
                      className="bg-purple-600 hover:bg-purple-500 text-white text-xs px-4 py-2 rounded-xl font-bold transition-all shadow-md flex items-center gap-1.5"
                    >
                      <UserCheck className="w-4 h-4" /> Take Over Chat
                    </button>
                  ) : (
                    <span className="bg-emerald-950 text-emerald-400 border border-emerald-800 text-xs px-3 py-1.5 rounded-xl font-bold flex items-center gap-1.5">
                      <CheckCircle2 className="w-4 h-4" /> Supervisor Active
                    </span>
                  )}
                </div>

                <div className="bg-purple-950/30 border border-purple-800/40 p-3 rounded-xl text-xs space-y-1">
                  <p className="text-purple-300 font-semibold flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5" /> AI Escalation Summary & Sentiment Context
                  </p>
                  <p className="text-slate-300">{selectedAlert.summary}</p>
                </div>
              </div>

              {/* Chat Replay Messages */}
              <div className="flex-1 overflow-y-auto space-y-3 pr-2 mb-4">
                {sessionMessages.map((m, idx) => (
                  <div
                    key={idx}
                    className={`flex gap-3 ${
                      m.role === "user"
                        ? "justify-start"
                        : m.role === "supervisor"
                        ? "justify-end"
                        : "justify-start"
                    }`}
                  >
                    <div
                      className={`p-3.5 rounded-2xl text-xs leading-relaxed max-w-[85%] ${
                        m.role === "user"
                          ? "bg-slate-800 text-slate-200 border border-slate-700"
                          : m.role === "supervisor"
                          ? "bg-purple-600 text-white font-medium shadow-md"
                          : "bg-blue-950/60 border border-blue-800 text-blue-200"
                      }`}
                    >
                      <p className="font-bold text-[10px] uppercase mb-1 opacity-70">
                        {m.role === "user" ? "Card Member" : m.role === "supervisor" ? "Human Supervisor" : "AI Agent"}
                      </p>
                      <p className="whitespace-pre-line">{m.content}</p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Live Takeover Input Bar */}
              {takenOver ? (
                <div className="flex gap-2 pt-3 border-t border-slate-800">
                  <input
                    type="text"
                    value={supervisorReply}
                    onChange={(e) => setSupervisorReply(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && sendSupervisorMessage()}
                    placeholder="Type message directly to Card Member..."
                    className="flex-1 bg-slate-900 text-white placeholder-slate-500 text-sm px-4 py-2.5 rounded-xl border border-purple-600 focus:outline-none"
                  />
                  <button
                    onClick={sendSupervisorMessage}
                    className="bg-purple-600 hover:bg-purple-500 text-white px-4 py-2.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5"
                  >
                    <Send className="w-4 h-4" /> Send Reply
                  </button>
                </div>
              ) : (
                <div className="bg-slate-900 p-3 rounded-xl text-center text-xs text-slate-400 border border-slate-800">
                  Click <span className="text-purple-400 font-bold">"Take Over Chat"</span> to intervene directly in this customer session.
                </div>
              )}
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-500 space-y-2">
              <MessageSquare className="w-10 h-10 opacity-40" />
              <p className="text-sm">Select an escalation alert to view conversation context</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
