"use client";

import { useState } from "react";
import {
  ShieldCheck,
  FileCode,
  CheckCircle2,
  Lock,
  Search,
  Filter,
  Layers,
  Database,
  ExternalLink,
  Cpu
} from "lucide-react";

interface AuditRecord {
  event_id: string;
  timestamp: string;
  topic: string;
  event_type: string;
  account_id: string;
  decision: "APPROVED" | "DENIED" | "ESCALATED" | "HIGH_SEVERITY";
  rule_id?: string;
  agent_reasoning: string;
  hash: string;
  payload: any;
}

export default function AuditExplorerPage() {
  const [topicFilter, setTopicFilter] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const sampleAuditEvents: AuditRecord[] = [
    {
      event_id: "evt-9a8b7c-1101",
      timestamp: new Date(Date.now() - 1000 * 60 * 3).toISOString(),
      topic: "compliance-decisions",
      event_type: "COMPLIANCE_DECISION",
      account_id: "a1111111-0000-0000-0000-000000000001",
      decision: "DENIED",
      rule_id: "RULE_FEE_WAIVER_FREQUENCY_12M",
      agent_reasoning: "Customer James Wilson already received an approved fee waiver within the past 12 months (used 3 months ago). Request DENIED per compliance rule.",
      hash: "8f7e2a...b4c91a",
      payload: {
        rule_id: "RULE_FEE_WAIVER_FREQUENCY_12M",
        decision: "denied",
        waivers_last_12m: 1,
        requested_amount: 35.0,
        policy_version: "v1.0"
      }
    },
    {
      event_id: "evt-4d5e6f-2202",
      timestamp: new Date(Date.now() - 1000 * 60 * 12).toISOString(),
      topic: "agent-actions",
      event_type: "FEE_WAIVER_EVALUATED",
      account_id: "a2222222-0000-0000-0000-000000000002",
      decision: "APPROVED",
      rule_id: "RULE_FEE_WAIVER_FREQUENCY_12M",
      agent_reasoning: "Customer Sarah Chen has 0 fee waivers in past 12 months. Request APPROVED for $35.00 late fee.",
      hash: "3b2a1c...f8e7d6",
      payload: {
        fee_type: "late_fee",
        amount_approved: 35.0,
        transaction_id: "TXN-CREDIT-WAIVER-001"
      }
    },
    {
      event_id: "evt-7g8h9i-3303",
      timestamp: new Date(Date.now() - 1000 * 60 * 25).toISOString(),
      topic: "card-events",
      event_type: "CARD_REPLACEMENT_INITIATED",
      account_id: "a3333333-0000-0000-0000-000000000003",
      decision: "HIGH_SEVERITY",
      rule_id: "RULE_CARD_FREEZE_LOST_STOLEN",
      agent_reasoning: "Card reported LOST. Old card ending in ****8899 immediately CANCELLED & FROZEN. Replacement issued to 55 Wall St.",
      hash: "1d2e3f...a9b8c7",
      payload: {
        reason: "lost",
        old_card_status: "cancelled",
        expedited: false,
        shipping_address: "55 Wall Street, New York, NY"
      }
    },
    {
      event_id: "evt-1j2k3l-4404",
      timestamp: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
      topic: "escalations",
      event_type: "HUMAN_ESCALATION_TRIGGERED",
      account_id: "a4444444-0000-0000-0000-000000000004",
      decision: "ESCALATED",
      rule_id: "RULE_HUMAN_SUPERVISOR_HANDOFF",
      agent_reasoning: "Customer requested supervisor handoff following credit limit increase denial.",
      hash: "9c8b7a...1f2e3d",
      payload: {
        reason: "policy_denied",
        conversation_turns: 4,
        context_snapshot: "Customer asked for human review"
      }
    }
  ];

  const [selectedEvent, setSelectedEvent] = useState<AuditRecord>(sampleAuditEvents[0]);

  const filteredEvents = sampleAuditEvents.filter((evt) => {
    const matchesTopic = topicFilter === "ALL" || evt.topic.includes(topicFilter.toLowerCase());
    const matchesSearch =
      evt.account_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      evt.agent_reasoning.toLowerCase().includes(searchQuery.toLowerCase()) ||
      evt.event_type.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesTopic && matchesSearch;
  });

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold text-white flex items-center gap-2">
              <ShieldCheck className="w-6 h-6 text-emerald-400" /> Immutable Audit Trail & Compliance Explorer
            </h1>
            <span className="bg-emerald-950 text-emerald-400 border border-emerald-800 text-xs px-2.5 py-0.5 rounded-full font-mono flex items-center gap-1">
              <Lock className="w-3 h-3" /> WORM Verified (Kafka {"->"} Elasticsearch)
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Verifiable audit log streaming every LLM decision, policy evaluation, and financial tool invocation
          </p>
        </div>

        <div className="flex items-center gap-3 font-mono text-xs text-slate-300">
          <div className="bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800 flex items-center gap-2">
            <Database className="w-4 h-4 text-blue-400" /> Elasticsearch: amex-audit-*
          </div>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 glass-panel p-4 rounded-2xl border border-slate-800">
        <div className="flex items-center gap-2">
          {["ALL", "COMPLIANCE", "AGENT-ACTIONS", "CARD-EVENTS", "ESCALATIONS"].map((t) => (
            <button
              key={t}
              onClick={() => setTopicFilter(t)}
              className={`px-3 py-1.5 rounded-xl text-xs font-mono transition-all ${
                topicFilter === t
                  ? "bg-emerald-600 text-white shadow-sm font-bold"
                  : "bg-slate-900 text-slate-400 hover:bg-slate-800"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="relative">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search account ID, event type, reasoning..."
            className="bg-slate-900 text-white placeholder-slate-500 text-xs pl-9 pr-4 py-2 rounded-xl border border-slate-800 focus:outline-none focus:border-emerald-500 w-64"
          />
        </div>
      </div>

      {/* Event Stream Table & Payload Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Stream Table (7 cols) */}
        <div className="lg:col-span-7 glass-panel rounded-2xl border border-slate-800 p-4 space-y-3">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
            <Layers className="w-4 h-4 text-emerald-400" /> Kafka Event Stream Records ({filteredEvents.length})
          </h2>

          <div className="space-y-2.5 overflow-y-auto max-h-[550px] pr-1">
            {filteredEvents.map((evt) => {
              const isSelected = selectedEvent?.event_id === evt.event_id;
              return (
                <div
                  key={evt.event_id}
                  onClick={() => setSelectedEvent(evt)}
                  className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-2 ${
                    isSelected
                      ? "bg-emerald-950/30 border-emerald-500 shadow-md"
                      : "bg-slate-900/80 border-slate-800 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-mono text-emerald-400 font-bold">{evt.event_type}</span>
                    <span className="text-[10px] text-slate-500 font-mono">
                      {new Date(evt.timestamp).toLocaleTimeString()}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-300 font-mono text-[11px]">Account: {evt.account_id.substring(0, 8)}...</span>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono ${
                        evt.decision === "APPROVED"
                          ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                          : evt.decision === "DENIED"
                          ? "bg-rose-950 text-rose-400 border border-rose-800"
                          : "bg-purple-950 text-purple-400 border border-purple-800"
                      }`}
                    >
                      {evt.decision}
                    </span>
                  </div>

                  <p className="text-xs text-slate-400 line-clamp-1">{evt.agent_reasoning}</p>

                  <div className="flex justify-between items-center text-[10px] text-slate-500 font-mono pt-1 border-t border-slate-800/60">
                    <span>Topic: {evt.topic}</span>
                    <span className="flex items-center gap-1 text-slate-400">
                      <Lock className="w-2.5 h-2.5 text-emerald-400" /> Hash: {evt.hash}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* JSON Payload Inspector (5 cols) */}
        <div className="lg:col-span-5 glass-panel rounded-2xl border border-slate-800 p-5 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <h3 className="font-semibold text-sm text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <FileCode className="w-4 h-4 text-blue-400" /> Event Cryptographic Payload
            </h3>
            <span className="text-[10px] bg-slate-900 text-slate-400 px-2 py-1 rounded font-mono">
              Event ID: {selectedEvent?.event_id}
            </span>
          </div>

          <div className="space-y-2 text-xs">
            <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1 font-mono">
              <p className="text-slate-400 text-[10px]">Deterministic Rule ID:</p>
              <p className="text-emerald-400 font-bold">{selectedEvent?.rule_id || "N/A"}</p>
            </div>

            <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1 font-mono">
              <p className="text-slate-400 text-[10px]">Agent Policy Reasoning:</p>
              <p className="text-slate-200 text-xs font-sans">{selectedEvent?.agent_reasoning}</p>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">Raw JSON Event Schema (WORM Logged)</p>
            <pre className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-[11px] font-mono text-blue-300 overflow-x-auto max-h-[300px]">
              {JSON.stringify(
                {
                  event_id: selectedEvent?.event_id,
                  event_timestamp: selectedEvent?.timestamp,
                  topic: selectedEvent?.topic,
                  event_type: selectedEvent?.event_type,
                  account_id: selectedEvent?.account_id,
                  rule_id: selectedEvent?.rule_id,
                  sha256_proof_hash: selectedEvent?.hash,
                  payload: selectedEvent?.payload
                },
                null,
                2
              )}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
