"use client";

import { useState, useEffect, useRef } from "react";
import {
  Send,
  User,
  Bot,
  CreditCard,
  Mic,
  MicOff,
  Sparkles,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ChevronRight,
  TrendingUp,
  DollarSign,
  Calendar,
  Volume2
} from "lucide-react";

interface Customer {
  account_id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string;
  account_status: string;
  credit_score: number;
  annual_income: number;
  credit_limit: number;
  current_balance: number;
  address_line1: string;
  city: string;
  state: string;
}

interface Message {
  id: string;
  sender: "user" | "bot" | "system";
  text: string;
  tools?: { name: string; content: string }[];
  timestamp: string;
}

export default function CustomerChatPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>("a1111111-0000-0000-0000-000000000001");
  const [currentCustomer, setCurrentCustomer] = useState<Customer | null>(null);
  
  const [channel, setChannel] = useState<"web" | "voice">("web");
  const [sessionId, setSessionId] = useState<string>("sess-" + Math.random().toString(36).substring(2, 9));
  
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "init",
      sender: "bot",
      text: "Welcome to American Express Customer Servicing. How can I assist you with your account today?",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    }
  ]);
  
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Fetch demo customers on mount
  useEffect(() => {
    fetch("http://localhost:8000/api/customers")
      .then((res) => res.json())
      .then((data) => {
        if (data.customers && data.customers.length > 0) {
          setCustomers(data.customers);
          const found = data.customers.find((c: Customer) => c.account_id === selectedAccount);
          setCurrentCustomer(found || data.customers[0]);
        }
      })
      .catch(() => {
        // Mock fallback if backend starting up
        const fallback: Customer[] = [
          {
            account_id: "a1111111-0000-0000-0000-000000000001",
            first_name: "James",
            last_name: "Wilson",
            email: "j.wilson@example.com",
            phone_number: "+12025550001",
            account_status: "active",
            credit_score: 750,
            annual_income: 120000,
            credit_limit: 25000,
            current_balance: 1820.49,
            address_line1: "742 Evergreen Terrace",
            city: "Springfield",
            state: "IL"
          },
          {
            account_id: "a2222222-0000-0000-0000-000000000002",
            first_name: "Sarah",
            last_name: "Chen",
            email: "s.chen@example.com",
            phone_number: "+12025550002",
            account_status: "active",
            credit_score: 620,
            annual_income: 48000,
            credit_limit: 3000,
            current_balance: 2815.12,
            address_line1: "100 Market St",
            city: "San Francisco",
            state: "CA"
          },
          {
            account_id: "a3333333-0000-0000-0000-000000000003",
            first_name: "Marcus",
            last_name: "Johnson",
            email: "m.johnson@example.com",
            phone_number: "+12025550003",
            account_status: "active",
            credit_score: 810,
            annual_income: 250000,
            credit_limit: 50000,
            current_balance: 5390.00,
            address_line1: "55 Wall Street",
            city: "New York",
            state: "NY"
          }
        ];
        setCustomers(fallback);
        setCurrentCustomer(fallback[0]);
      });
  }, []);

  // Update selected customer details
  const handleCustomerChange = (accId: string) => {
    setSelectedAccount(accId);
    const found = customers.find((c) => c.account_id === accId);
    if (found) setCurrentCustomer(found);
    
    // Reset session for new persona
    const newSess = "sess-" + Math.random().toString(36).substring(2, 9);
    setSessionId(newSess);
    setMessages([
      {
        id: Math.random().toString(),
        sender: "bot",
        text: `Welcome back ${found?.first_name || "Card Member"}. How can I assist you with your ${found?.credit_limit ? "$" + found.credit_limit.toLocaleString() : ""} credit line today?`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      }
    ]);
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleStartRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/wav" });
        const formData = new FormData();
        formData.append("file", audioBlob, "audio.wav");

        setIsVoiceActive(true);
        try {
          const sttRes = await fetch("http://localhost:8000/api/stt", {
            method: "POST",
            body: formData,
          });
          const sttData = await sttRes.json();
          if (sttData.transcript) {
            sendMessage(sttData.transcript);
          }
        } catch (e) {
          console.error("STT Error", e);
        }
        setIsVoiceActive(false);
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (e) {
      console.error("Microphone access denied", e);
    }
  };

  const handleStopRecording = () => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
    }
    setIsRecording(false);
  };

  const sendMessage = async (textToSend?: string) => {
    const query = textToSend || input;
    if (!query.trim() || loading) return;

    const userMsg: Message = {
      id: Math.random().toString(),
      sender: "user",
      text: query,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInput("");
    setLoading(true);

    try {
      const response = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_id: selectedAccount,
          session_id: sessionId,
          message: query,
          channel: channel
        })
      });

      const data = await response.json();
      
      const botMsg: Message = {
        id: Math.random().toString(),
        sender: "bot",
        text: data.reply || "Your request has been processed.",
        tools: data.tools_executed,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      };

      setMessages((prev) => [...prev, botMsg]);

      // Sarvam AI TTS readout if voice channel active
      if (channel === "voice") {
        try {
          const ttsRes = await fetch("http://localhost:8000/api/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              text: data.reply,
              target_language_code: "hi-IN",
              speaker: "shubh"
            })
          });
          const ttsData = await ttsRes.json();
          if (ttsData && ttsData.audios && ttsData.audios.length > 0) {
            const audio = new Audio("data:audio/wav;base64," + ttsData.audios[0]);
            audio.play();
          }
        } catch (e) {
          console.error("TTS Error", e);
        }
      }
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          id: Math.random().toString(),
          sender: "system",
          text: "Connection error: Unable to reach AI Servicing backend.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const triggerQuickAction = (text: string) => {
    sendMessage(text);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* LEFT / MAIN CHAT AREA (8 cols) */}
      <div className="lg:col-span-8 flex flex-col h-[calc(100vh-140px)]">
        {/* Top Control Bar */}
        <div className="glass-panel p-4 rounded-2xl mb-4 flex flex-wrap items-center justify-between gap-4 border-b border-slate-800">
          {/* Customer Switcher Dropdown */}
          <div className="flex items-center gap-3">
            <User className="w-5 h-5 text-blue-400" />
            <div>
              <label className="block text-[10px] text-slate-400 font-semibold uppercase tracking-wider">
                Simulated Card Member Login
              </label>
              <select
                value={selectedAccount}
                onChange={(e) => handleCustomerChange(e.target.value)}
                className="bg-slate-900 text-white font-medium text-sm rounded-lg px-3 py-1.5 border border-slate-700 focus:outline-none focus:border-blue-500 cursor-pointer"
              >
                {customers.map((c) => (
                  <option key={c.account_id} value={c.account_id}>
                    {c.first_name} {c.last_name} (Score: {c.credit_score})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Channel Mode Toggle (Web vs Voice Gateway Simulator) */}
          <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800">
            <button
              onClick={() => setChannel("web")}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                channel === "web"
                  ? "bg-blue-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <CreditCard className="w-3.5 h-3.5" /> Web Chat
            </button>
            <button
              onClick={() => setChannel("voice")}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                channel === "voice"
                  ? "bg-purple-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Mic className="w-3.5 h-3.5" /> Voice Gateway (Twilio)
            </button>
          </div>
        </div>

        {/* Voice Gateway Audio Wave Banner */}
        {channel === "voice" && (
          <div className="bg-purple-950/40 border border-purple-800/40 rounded-xl p-3 mb-4 flex items-center justify-between text-purple-300 text-xs">
            <div className="flex items-center gap-3">
              <div className="relative flex items-center justify-center h-8 w-8 rounded-full bg-purple-900/60">
                <Volume2 className="w-4 h-4 text-purple-300 animate-pulse" />
              </div>
              <div>
                <p className="font-semibold text-purple-200">Voice Gateway Active (AWS Connect / Twilio Simulator)</p>
                <p className="text-[11px] text-purple-400">Speech Synth output enabled for synthetic call turn evaluation</p>
              </div>
            </div>
            <div className="flex gap-1 items-end h-5">
              <span className="w-1 bg-purple-400 h-2 animate-bounce"></span>
              <span className="w-1 bg-purple-400 h-5 animate-bounce [animation-delay:0.2s]"></span>
              <span className="w-1 bg-purple-400 h-3 animate-bounce [animation-delay:0.4s]"></span>
              <span className="w-1 bg-purple-400 h-4 animate-bounce [animation-delay:0.1s]"></span>
            </div>
          </div>
        )}

        {/* Messages Container */}
        <div className="flex-1 glass-panel rounded-2xl p-4 overflow-y-auto space-y-4 mb-4">
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex gap-3 ${m.sender === "user" ? "justify-end" : "justify-start"}`}
            >
              {m.sender !== "user" && (
                <div className="h-8 w-8 rounded-xl amex-gradient flex items-center justify-center text-white shrink-0 mt-1 shadow-md">
                  <Bot className="w-4 h-4" />
                </div>
              )}

              <div className={`max-w-[80%] space-y-2`}>
                <div
                  className={`p-4 rounded-2xl text-sm leading-relaxed ${
                    m.sender === "user"
                      ? "bg-blue-600 text-white rounded-tr-none shadow-md"
                      : m.sender === "system"
                      ? "bg-rose-950/60 border border-rose-800 text-rose-300"
                      : "bg-slate-800/90 text-slate-100 rounded-tl-none border border-slate-700/60"
                  }`}
                >
                  <p className="whitespace-pre-line">{m.text}</p>

                  {/* Tool Execution Badges */}
                  {m.tools && m.tools.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-slate-700/50 space-y-2">
                      <p className="text-[10px] font-mono uppercase tracking-wider text-blue-400 flex items-center gap-1 font-semibold">
                        <Sparkles className="w-3 h-3" /> Policy Engine Executed Tools:
                      </p>
                      {m.tools.map((t, i) => (
                        <div
                          key={i}
                          className="bg-slate-950/80 p-2.5 rounded-xl border border-slate-700 text-xs font-mono text-slate-300 space-y-1"
                        >
                          <div className="flex items-center justify-between text-blue-300 font-bold">
                            <span>{t.name}</span>
                            <span className="bg-blue-900/40 text-blue-300 px-1.5 py-0.5 rounded text-[10px]">
                              Determined Zero-Hallucination
                            </span>
                          </div>
                          <p className="text-slate-400 text-[11px] font-sans">{t.content}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <p
                  className={`text-[10px] text-slate-500 font-mono ${
                    m.sender === "user" ? "text-right" : "text-left"
                  }`}
                >
                  {m.timestamp}
                </p>
              </div>

              {m.sender === "user" && (
                <div className="h-8 w-8 rounded-xl bg-slate-700 flex items-center justify-center text-slate-200 shrink-0 mt-1">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex gap-3 items-center">
              <div className="h-8 w-8 rounded-xl amex-gradient flex items-center justify-center text-white shrink-0 shadow-md">
                <Bot className="w-4 h-4" />
              </div>
              <div className="bg-slate-800/90 p-4 rounded-2xl rounded-tl-none border border-slate-700/60 flex items-center gap-2">
                <span className="h-2 w-2 bg-blue-400 rounded-full animate-ping"></span>
                <span className="text-xs text-slate-400 font-mono">Evaluating Compliance Rules & Policy Engine...</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick Action Pills */}
        <div className="flex gap-2 overflow-x-auto pb-2 mb-2 scrollbar-none">
          <button
            onClick={() => triggerQuickAction("Can you please waive my $35 late fee?")}
            className="bg-slate-900 hover:bg-slate-800 text-blue-300 text-xs px-3 py-1.5 rounded-xl border border-slate-800 whitespace-nowrap transition-colors flex items-center gap-1.5"
          >
            <DollarSign className="w-3.5 h-3.5 text-blue-400" /> Waive Late Fee ($35)
          </button>
          <button
            onClick={() => triggerQuickAction("I want to request a credit limit increase to $50,000. My annual income is $250,000.")}
            className="bg-slate-900 hover:bg-slate-800 text-emerald-300 text-xs px-3 py-1.5 rounded-xl border border-slate-800 whitespace-nowrap transition-colors flex items-center gap-1.5"
          >
            <TrendingUp className="w-3.5 h-3.5 text-emerald-400" /> Request Limit Increase
          </button>
          <button
            onClick={() => triggerQuickAction("I lost my card in New York! Please freeze it and send a replacement to 55 Wall St.")}
            className="bg-slate-900 hover:bg-slate-800 text-rose-300 text-xs px-3 py-1.5 rounded-xl border border-slate-800 whitespace-nowrap transition-colors flex items-center gap-1.5"
          >
            <ShieldAlert className="w-3.5 h-3.5 text-rose-400" /> Report Lost/Stolen Card
          </button>
          <button
            onClick={() => triggerQuickAction("I am traveling to Tokyo from 2026-08-01 to 2026-08-15.")}
            className="bg-slate-900 hover:bg-slate-800 text-amber-300 text-xs px-3 py-1.5 rounded-xl border border-slate-800 whitespace-nowrap transition-colors flex items-center gap-1.5"
          >
            <Calendar className="w-3.5 h-3.5 text-amber-400" /> Travel Notification
          </button>
          <button
            onClick={() => triggerQuickAction("I am unsatisfied with this response. Transfer me to a human supervisor manager right now.")}
            className="bg-slate-900 hover:bg-slate-800 text-purple-300 text-xs px-3 py-1.5 rounded-xl border border-slate-800 whitespace-nowrap transition-colors flex items-center gap-1.5"
          >
            <AlertTriangle className="w-3.5 h-3.5 text-purple-400" /> Escalate to Human
          </button>
        </div>

        {/* Message Input Box */}
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            placeholder={channel === "voice" ? "Speak or type voice command..." : "Type your servicing request..."}
            className="flex-1 bg-slate-900 text-white placeholder-slate-500 text-sm px-4 py-3 rounded-xl border border-slate-700/80 focus:outline-none focus:border-blue-500 transition-colors"
          />
          {channel === "voice" && (
            <button
              onClick={isRecording ? handleStopRecording : handleStartRecording}
              className={`px-4 py-3 rounded-xl transition-all flex items-center justify-center ${
                isRecording
                  ? "bg-rose-600 hover:bg-rose-500 text-white animate-pulse"
                  : "bg-slate-800 hover:bg-slate-700 text-slate-300"
              }`}
            >
              {isRecording ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
            </button>
          )}
          <button
            onClick={() => sendMessage()}
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-5 py-3 rounded-xl font-medium text-sm transition-all flex items-center gap-2 shadow-lg glow-blue"
          >
            <Send className="w-4 h-4" /> Send
          </button>
        </div>
      </div>

      {/* RIGHT SIDEBAR: Live Customer Account Profile (4 cols) */}
      <div className="lg:col-span-4 space-y-4">
        {/* Customer Card */}
        <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <h2 className="font-semibold text-sm text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <CreditCard className="w-4 h-4 text-blue-400" /> Card Member Profile
            </h2>
            <span
              className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${
                currentCustomer?.account_status === "active"
                  ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                  : "bg-rose-950 text-rose-400 border border-rose-800"
              }`}
            >
              {currentCustomer?.account_status || "Active"}
            </span>
          </div>

          <div className="space-y-3">
            <div>
              <p className="text-xl font-bold text-white">
                {currentCustomer?.first_name} {currentCustomer?.last_name}
              </p>
              <p className="text-xs text-slate-400">{currentCustomer?.email}</p>
            </div>

            {/* Credit Score Gauge */}
            <div className="bg-slate-900/80 p-3.5 rounded-xl border border-slate-800 space-y-2">
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-400">Credit Score</span>
                <span className="font-bold text-white text-sm">{currentCustomer?.credit_score || 700}</span>
              </div>
              <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    (currentCustomer?.credit_score || 700) > 700
                      ? "bg-emerald-500"
                      : (currentCustomer?.credit_score || 700) > 600
                      ? "bg-amber-500"
                      : "bg-rose-500"
                  }`}
                  style={{ width: `${Math.min(100, (((currentCustomer?.credit_score || 700) - 300) / 550) * 100)}%` }}
                ></div>
              </div>
              <p className="text-[10px] text-slate-500 font-mono">
                {(currentCustomer?.credit_score || 700) > 700
                  ? "Eligible for automatic CLI risk models (>700)"
                  : "Ineligible for CLI risk models (Score <= 700)"}
              </p>
            </div>

            {/* Financial Overview Metrics */}
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800">
                <p className="text-[10px] text-slate-400">Credit Limit</p>
                <p className="text-sm font-bold text-emerald-400">
                  ${currentCustomer?.credit_limit ? currentCustomer.credit_limit.toLocaleString() : "0"}
                </p>
              </div>
              <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800">
                <p className="text-[10px] text-slate-400">Annual Income</p>
                <p className="text-sm font-bold text-white">
                  ${currentCustomer?.annual_income ? currentCustomer.annual_income.toLocaleString() : "0"}
                </p>
              </div>
            </div>

            {/* Address */}
            <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800 text-xs">
              <p className="text-[10px] text-slate-400 mb-1">On-File Shipping Address</p>
              <p className="text-slate-200 font-medium">{currentCustomer?.address_line1}</p>
              <p className="text-slate-400">{currentCustomer?.city}, {currentCustomer?.state}</p>
            </div>
          </div>
        </div>

        {/* Compliance Guarantees Box */}
        <div className="glass-panel p-4 rounded-2xl border border-slate-800 space-y-2 text-xs">
          <h3 className="font-semibold text-slate-300 flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Compliance & Audit Controls
          </h3>
          <ul className="text-slate-400 space-y-1.5 text-[11px] list-disc list-inside">
            <li>Zero LLM financial hallucinations</li>
            <li>Immutable Kafka stream logging</li>
            <li>Automatic card freeze on lost status</li>
            <li>Context handoff on escalation</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
