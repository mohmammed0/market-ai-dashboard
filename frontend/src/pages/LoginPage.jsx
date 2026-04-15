import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { checkAuthStatus, login } from "../api/auth";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    checkAuthStatus()
      .then((status) => {
        if (active && status?.auth_enabled === false) {
          navigate("/", { replace: true });
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [navigate]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "var(--color-void, #0a0a0f)",
      direction: "rtl",
    }}>
      <div style={{
        width: "100%",
        maxWidth: 400,
        padding: "var(--space-8, 32px)",
        background: "var(--color-surface-1, #1a1a2e)",
        borderRadius: "var(--radius-lg, 12px)",
        boxShadow: "var(--shadow-xl)",
      }}>
        <div style={{ textAlign: "center", marginBottom: "var(--space-6, 24px)" }}>
          <h1 style={{
            fontSize: "1.75rem",
            fontWeight: 700,
            color: "var(--color-text-primary, #e0e0e0)",
            margin: 0,
          }}>
            Market AI
          </h1>
          <p style={{
            fontSize: "0.875rem",
            color: "var(--color-text-tertiary, #888)",
            marginTop: "var(--space-2, 8px)",
          }}>
            سجّل دخولك للمتابعة
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          {error && (
            <div style={{
              padding: "var(--space-3, 12px)",
              marginBottom: "var(--space-4, 16px)",
              background: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "var(--radius-md, 8px)",
              color: "var(--color-negative, #ef4444)",
              fontSize: "0.875rem",
              textAlign: "center",
            }}>
              {error}
            </div>
          )}

          <div style={{ marginBottom: "var(--space-4, 16px)" }}>
            <label style={{
              display: "block",
              fontSize: "0.875rem",
              color: "var(--color-text-secondary, #aaa)",
              marginBottom: "var(--space-2, 8px)",
            }}>
              اسم المستخدم
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              autoComplete="username"
              style={{
                width: "100%",
                padding: "var(--space-3, 12px)",
                background: "var(--color-surface-0, #12121e)",
                border: "1px solid var(--color-border, #333)",
                borderRadius: "var(--radius-md, 8px)",
                color: "var(--color-text-primary, #e0e0e0)",
                fontSize: "1rem",
                outline: "none",
                boxSizing: "border-box",
                direction: "ltr",
                textAlign: "left",
              }}
            />
          </div>

          <div style={{ marginBottom: "var(--space-6, 24px)" }}>
            <label style={{
              display: "block",
              fontSize: "0.875rem",
              color: "var(--color-text-secondary, #aaa)",
              marginBottom: "var(--space-2, 8px)",
            }}>
              كلمة المرور
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              style={{
                width: "100%",
                padding: "var(--space-3, 12px)",
                background: "var(--color-surface-0, #12121e)",
                border: "1px solid var(--color-border, #333)",
                borderRadius: "var(--radius-md, 8px)",
                color: "var(--color-text-primary, #e0e0e0)",
                fontSize: "1rem",
                outline: "none",
                boxSizing: "border-box",
                direction: "ltr",
                textAlign: "left",
              }}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              padding: "var(--space-3, 12px)",
              background: loading ? "var(--color-surface-2, #2a2a3e)" : "var(--color-positive, #22c55e)",
              color: loading ? "var(--color-text-tertiary)" : "#000",
              border: "none",
              borderRadius: "var(--radius-md, 8px)",
              fontSize: "1rem",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
              transition: "background 0.2s",
            }}
          >
            {loading ? "جاري الدخول..." : "دخول"}
          </button>
        </form>
      </div>
    </div>
  );
}
