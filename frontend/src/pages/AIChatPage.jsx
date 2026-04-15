/**
 * AIChatPage — المساعد الذكي للأسواق المالية
 * واجهة دردشة عربية RTL مع دعم تحليل الأسهم
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { postJson } from "../api/client";

// ─── Constants ────────────────────────────────────────────────────────────────

const SUGGESTED_QUESTIONS = [
  "تحليل AAPL",
  "تحليل AAPL",
  "تحليل TSLA",
  "كيف السوق اليوم؟",
  "قارن AAPL و NVDA و TSLA",
  "أفضل سهم الآن",
];

const WELCOME_MESSAGE = {
  id: "welcome",
  role: "assistant",
  content:
    "مرحباً! أنا **المحلل الذكي المتقدم** للأسواق المالية 🤖\n\n" +
    "أقدم لك تحليل احترافي متقدم يشمل:\n" +
    "📊 15+ مؤشر فني — RSI, MACD, ADX, بولينجر, فيبوناتشي, VWAP\n" +
    "📈 كشف أنماط الشارت + 3 دعوم و 3 مقاومات\n" +
    "🎯 إشارات تداول مع خطة دخول وأهداف ربح\n" +
    "⚖️ تحليل مخاطر — تقلب سنوي وأقصى انخفاض\n\n" +
    "جرب أحد الأسئلة أو اكتب رمز أي سهم! 🚀",
  timestamp: new Date().toISOString(),
};

// ─── Styles ───────────────────────────────────────────────────────────────────

const S = {
  page: {
    display: "flex",
    flexDirection: "column",
    height: "calc(100vh - 48px)",
    background: "#020617",
    color: "#f1f5f9",
    fontFamily: "'Cairo', 'Inter', sans-serif",
    direction: "rtl",
    overflow: "hidden",
  },
  header: {
    background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
    borderBottom: "1px solid #1e3a5f",
    padding: "14px 20px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    flexShrink: 0,
  },
  headerTitle: {
    display: "flex",
    alignItems: "center",
    gap: 12,
  },
  titleIcon: {
    width: 38,
    height: 38,
    borderRadius: 10,
    background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 20,
    flexShrink: 0,
  },
  titleText: {
    fontSize: 18,
    fontWeight: 700,
    color: "#f1f5f9",
  },
  titleSub: {
    fontSize: 12,
    color: "#64748b",
    marginTop: 1,
  },
  clearBtn: {
    padding: "6px 14px",
    borderRadius: 8,
    border: "1px solid #334155",
    background: "transparent",
    color: "#94a3b8",
    fontSize: 13,
    cursor: "pointer",
    transition: "all 0.2s",
    display: "flex",
    alignItems: "center",
    gap: 6,
  },
  chatArea: {
    flex: 1,
    overflowY: "auto",
    padding: "20px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  suggestionsWrap: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    justifyContent: "center",
    padding: "8px 0 4px",
  },
  suggestionBtn: {
    padding: "8px 16px",
    borderRadius: 20,
    border: "1px solid #1e3a5f",
    background: "rgba(59,130,246,0.08)",
    color: "#93c5fd",
    fontSize: 13,
    cursor: "pointer",
    transition: "all 0.2s",
    whiteSpace: "nowrap",
  },
  msgRow: (role) => ({
    display: "flex",
    justifyContent: role === "user" ? "flex-start" : "flex-end",
    alignItems: "flex-end",
    gap: 8,
  }),
  bubble: (role) => ({
    maxWidth: "75%",
    padding: "12px 16px",
    borderRadius: role === "user" ? "16px 4px 16px 16px" : "4px 16px 16px 16px",
    background: role === "user"
      ? "linear-gradient(135deg, #1d4ed8, #2563eb)"
      : "linear-gradient(135deg, #1e293b, #0f172a)",
    border: role === "user" ? "none" : "1px solid #1e3a5f",
    color: "#f1f5f9",
    fontSize: 14,
    lineHeight: 1.7,
    boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
    wordBreak: "break-word",
    whiteSpace: "pre-wrap",
  }),
  avatar: (role) => ({
    width: 32,
    height: 32,
    borderRadius: "50%",
    background: role === "user"
      ? "linear-gradient(135deg, #1d4ed8, #60a5fa)"
      : "linear-gradient(135deg, #7c3aed, #a78bfa)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 14,
    flexShrink: 0,
  }),
  timestamp: {
    fontSize: 10,
    color: "#475569",
    marginTop: 4,
    textAlign: "center",
  },
  typingDots: {
    display: "flex",
    gap: 4,
    padding: "14px 18px",
    background: "linear-gradient(135deg, #1e293b, #0f172a)",
    border: "1px solid #1e3a5f",
    borderRadius: "4px 16px 16px 16px",
    alignSelf: "flex-end",
  },
  dot: (delay) => ({
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: "#60a5fa",
    animation: "bounce 1.2s infinite",
    animationDelay: delay,
  }),
  priceCard: {
    marginTop: 10,
    padding: "10px 14px",
    borderRadius: 10,
    background: "rgba(59,130,246,0.1)",
    border: "1px solid #1e3a5f",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  priceCardSymbol: {
    fontSize: 16,
    fontWeight: 700,
    color: "#60a5fa",
    fontFamily: "monospace",
  },
  priceCardPrice: {
    fontSize: 18,
    fontWeight: 700,
    color: "#f1f5f9",
  },
  priceCardChg: (pct) => ({
    fontSize: 13,
    fontWeight: 600,
    color: (pct >= 0) ? "#4ade80" : "#f87171",
    display: "flex",
    alignItems: "center",
    gap: 4,
  }),
  inputArea: {
    padding: "12px 16px",
    borderTop: "1px solid #1e3a5f",
    background: "#0f172a",
    display: "flex",
    alignItems: "flex-end",
    gap: 10,
    flexShrink: 0,
  },
  textarea: {
    flex: 1,
    padding: "10px 14px",
    borderRadius: 12,
    border: "1px solid #334155",
    background: "#1e293b",
    color: "#f1f5f9",
    fontSize: 14,
    fontFamily: "'Cairo', 'Inter', sans-serif",
    resize: "none",
    outline: "none",
    lineHeight: 1.5,
    minHeight: 42,
    maxHeight: 120,
    direction: "rtl",
    transition: "border-color 0.2s",
  },
  sendBtn: (disabled) => ({
    width: 42,
    height: 42,
    borderRadius: 12,
    border: "none",
    background: disabled
      ? "#1e293b"
      : "linear-gradient(135deg, #3b82f6, #8b5cf6)",
    color: disabled ? "#475569" : "#fff",
    cursor: disabled ? "not-allowed" : "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    transition: "all 0.2s",
    fontSize: 18,
  }),
};

// ─── Mini Price Card ──────────────────────────────────────────────────────────

function PriceCard({ symbol, quote }) {
  if (!quote) return null;
  const pct = quote.change_pct ?? 0;
  const sign = pct >= 0 ? "+" : "";
  return (
    <div style={S.priceCard}>
      <span style={S.priceCardSymbol}>{symbol}</span>
      <span style={S.priceCardPrice}>${Number(quote.price).toFixed(2)}</span>
      <span style={S.priceCardChg(pct)}>
        {pct >= 0 ? "📈" : "📉"} {sign}{Number(pct).toFixed(2)}%
      </span>
    </div>
  );
}

// ─── Formatted Message Content ───────────────────────────────────────────────

function MsgContent({ content, data }) {
  // Bold **text**
  const renderBold = (text) => {
    const parts = text.split(/\*\*(.*?)\*\*/g);
    return parts.map((part, i) =>
      i % 2 === 1
        ? <strong key={i} style={{ color: "#93c5fd" }}>{part}</strong>
        : <span key={i}>{part}</span>
    );
  };

  const lines = content.split("\n");
  return (
    <div>
      {lines.map((line, i) => (
        <div key={i} style={{ minHeight: line === "" ? "0.6em" : undefined }}>
          {renderBold(line)}
        </div>
      ))}
      {data?.symbol && data?.quote && (
        <PriceCard symbol={data.symbol} quote={data.quote} />
      )}
    </div>
  );
}

// ─── Typing indicator ─────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "flex-end", gap: 8 }}>
      <div style={S.avatar("assistant")}>🤖</div>
      <div style={S.typingDots}>
        <div style={S.dot("0s")} />
        <div style={S.dot("0.2s")} />
        <div style={S.dot("0.4s")} />
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function AIChatPage() {
  const [messages, setMessages] = useState([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const chatEndRef = useRef(null);
  const textareaRef = useRef(null);

  // Auto-scroll to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Auto-resize textarea
  const handleTextareaChange = (e) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
  };

  const sendMessage = useCallback(async (text) => {
    const trimmed = (text || input).trim();
    if (!trimmed || loading) return;

    setInput("");
    setShowSuggestions(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = "42px";
    }

    const userMsg = {
      id: Date.now().toString(),
      role: "user",
      content: trimmed,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      // Build history (last 10 exchanges max)
      const history = messages
        .filter((m) => m.id !== "welcome")
        .slice(-10)
        .map((m) => ({ role: m.role, content: m.content }));

      const result = await postJson("/api/ai-chat/message", {
        message: trimmed,
        symbol: null,
        history,
      });

      const assistantMsg = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: result.reply || "لم أتمكن من الإجابة في الوقت الحالي.",
        timestamp: new Date().toISOString(),
        data: result.data || {},
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: "⚠️ حدث خطأ في الاتصال بالخادم. يرجى المحاولة مجدداً.",
          timestamp: new Date().toISOString(),
          data: {},
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, messages]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearChat = () => {
    setMessages([WELCOME_MESSAGE]);
    setShowSuggestions(true);
    setInput("");
  };

  const formatTime = (iso) => {
    try {
      return new Intl.DateTimeFormat("ar-SA", {
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(iso));
    } catch {
      return "";
    }
  };

  return (
    <>
      {/* Bounce animation for typing dots */}
      <style>{`
        @keyframes bounce {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.6; }
          30% { transform: translateY(-6px); opacity: 1; }
        }
        .ai-suggestion-btn:hover {
          background: rgba(59,130,246,0.2) !important;
          border-color: #3b82f6 !important;
          color: #bfdbfe !important;
        }
        .ai-clear-btn:hover {
          background: rgba(239,68,68,0.1) !important;
          border-color: #ef4444 !important;
          color: #fca5a5 !important;
        }
        .ai-textarea:focus {
          border-color: #3b82f6 !important;
        }
        .ai-send-btn:not(:disabled):hover {
          transform: scale(1.05);
          box-shadow: 0 4px 12px rgba(59,130,246,0.4);
        }
      `}</style>

      <div style={S.page}>
        {/* Header */}
        <div style={S.header}>
          <div style={S.headerTitle}>
            <div style={S.titleIcon}>🤖</div>
            <div>
              <div style={S.titleText}>المساعد الذكي</div>
              <div style={S.titleSub}>تحليل الأسهم والأسواق بالذكاء الاصطناعي</div>
            </div>
          </div>
          <button
            className="ai-clear-btn"
            style={S.clearBtn}
            onClick={clearChat}
            title="مسح المحادثة"
          >
            🗑 مسح
          </button>
        </div>

        {/* Chat Messages */}
        <div style={S.chatArea}>
          {messages.map((msg) => (
            <div key={msg.id} style={{ display: "flex", flexDirection: "column" }}>
              <div style={S.msgRow(msg.role)}>
                {msg.role === "assistant" && (
                  <div style={S.avatar("assistant")}>🤖</div>
                )}
                <div style={S.bubble(msg.role)}>
                  <MsgContent content={msg.content} data={msg.data} />
                </div>
                {msg.role === "user" && (
                  <div style={S.avatar("user")}>👤</div>
                )}
              </div>
              <div style={{
                ...S.timestamp,
                textAlign: msg.role === "user" ? "left" : "right",
                paddingLeft: msg.role === "user" ? 40 : 0,
                paddingRight: msg.role === "assistant" ? 40 : 0,
              }}>
                {formatTime(msg.timestamp)}
              </div>
            </div>
          ))}

          {loading && <TypingIndicator />}

          {/* Suggested questions (shown at start) */}
          {showSuggestions && messages.length <= 1 && !loading && (
            <div style={{ marginTop: 8 }}>
              <div style={{ textAlign: "center", color: "#475569", fontSize: 12, marginBottom: 10 }}>
                أسئلة مقترحة
              </div>
              <div style={S.suggestionsWrap}>
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    className="ai-suggestion-btn"
                    style={S.suggestionBtn}
                    onClick={() => sendMessage(q)}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Input Area */}
        <div style={S.inputArea}>
          <textarea
            ref={textareaRef}
            className="ai-textarea"
            style={S.textarea}
            rows={1}
            placeholder="اسأل عن سهم أو السوق... (مثال: ما سعر AAPL؟)"
            value={input}
            onChange={handleTextareaChange}
            onKeyDown={handleKeyDown}
            disabled={loading}
            dir="rtl"
          />
          <button
            className="ai-send-btn"
            style={S.sendBtn(!input.trim() || loading)}
            onClick={() => sendMessage()}
            disabled={!input.trim() || loading}
            title="إرسال"
          >
            {loading ? "⏳" : "➤"}
          </button>
        </div>
      </div>
    </>
  );
}
