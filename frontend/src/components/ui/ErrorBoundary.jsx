import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: "var(--space-8, 32px)",
          textAlign: "center",
          direction: "rtl",
        }}>
          <div style={{
            maxWidth: 480,
            margin: "0 auto",
            padding: "var(--space-6, 24px)",
            background: "var(--color-surface-1, #1a1a2e)",
            borderRadius: "var(--radius-lg, 12px)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
          }}>
            <h2 style={{
              color: "var(--color-negative, #ef4444)",
              fontSize: "1.25rem",
              margin: "0 0 var(--space-3, 12px)",
            }}>
              حدث خطأ غير متوقع
            </h2>
            <p style={{
              color: "var(--color-text-secondary, #aaa)",
              fontSize: "0.875rem",
              margin: "0 0 var(--space-4, 16px)",
            }}>
              {this.state.error?.message || "حدث خطأ أثناء تحميل الصفحة"}
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
              style={{
                padding: "var(--space-2, 8px) var(--space-5, 20px)",
                background: "var(--color-surface-2, #2a2a3e)",
                color: "var(--color-text-primary, #e0e0e0)",
                border: "1px solid var(--color-border, #333)",
                borderRadius: "var(--radius-md, 8px)",
                cursor: "pointer",
                fontSize: "0.875rem",
              }}
            >
              إعادة تحميل الصفحة
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
