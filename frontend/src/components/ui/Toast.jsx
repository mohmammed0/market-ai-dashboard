import { useState, useCallback, createContext, useContext } from "react";

const ToastContext = createContext(null);

let _toastIdCounter = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type = "info", duration = 4000) => {
    const id = ++_toastIdCounter;
    setToasts((prev) => [...prev.slice(-4), { id, message, type }]);
    if (duration > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, duration);
    }
    return id;
  }, []);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toastApi = {
    success: (msg) => addToast(msg, "success"),
    error: (msg) => addToast(msg, "error", 6000),
    warning: (msg) => addToast(msg, "warning", 5000),
    info: (msg) => addToast(msg, "info"),
  };

  return (
    <ToastContext.Provider value={toastApi}>
      {children}
      <div style={{
        position: "fixed",
        top: "var(--space-4, 16px)",
        left: "var(--space-4, 16px)",
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-2, 8px)",
        direction: "rtl",
        pointerEvents: "none",
      }}>
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onClose={() => removeToast(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

const TYPE_STYLES = {
  success: { bg: "rgba(34, 197, 94, 0.15)", border: "rgba(34, 197, 94, 0.4)", icon: "✓", color: "#22c55e" },
  error: { bg: "rgba(239, 68, 68, 0.15)", border: "rgba(239, 68, 68, 0.4)", icon: "✕", color: "#ef4444" },
  warning: { bg: "rgba(245, 158, 11, 0.15)", border: "rgba(245, 158, 11, 0.4)", icon: "!", color: "#f59e0b" },
  info: { bg: "rgba(59, 130, 246, 0.15)", border: "rgba(59, 130, 246, 0.4)", icon: "i", color: "#3b82f6" },
};

function ToastItem({ toast, onClose }) {
  const style = TYPE_STYLES[toast.type] || TYPE_STYLES.info;
  return (
    <div style={{
      padding: "var(--space-3, 12px) var(--space-4, 16px)",
      background: style.bg,
      backdropFilter: "blur(12px)",
      border: `1px solid ${style.border}`,
      borderRadius: "var(--radius-md, 8px)",
      color: "var(--color-text-primary, #e0e0e0)",
      fontSize: "0.875rem",
      display: "flex",
      alignItems: "center",
      gap: "var(--space-3, 12px)",
      minWidth: 280,
      maxWidth: 420,
      pointerEvents: "auto",
      boxShadow: "var(--shadow-lg)",
      animation: "slideIn 0.25s ease-out",
    }}>
      <span style={{
        width: 22,
        height: 22,
        borderRadius: "50%",
        background: style.color,
        color: "#000",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "0.75rem",
        fontWeight: 700,
        flexShrink: 0,
      }}>
        {style.icon}
      </span>
      <span style={{ flex: 1 }}>{toast.message}</span>
      <button
        onClick={onClose}
        style={{
          background: "none",
          border: "none",
          color: "var(--color-text-tertiary, #666)",
          cursor: "pointer",
          padding: 4,
          fontSize: "1rem",
          lineHeight: 1,
          flexShrink: 0,
        }}
      >
        ×
      </button>
    </div>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
