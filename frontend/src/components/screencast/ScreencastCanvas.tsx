import React, { useEffect, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import { Monitor, Send, CornerDownLeft, ArrowRightToLine, Delete, X, AlertTriangle, ShieldAlert } from "lucide-react";
import { apiPost } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ScreencastCanvasProps {
  site: "naukri" | "linkedin";
  mode?: "login" | "live_check";
  fps?: number;
  onClose?: () => void;
  onSaved?: () => void;
  onReady?: () => void;
}

export default function ScreencastCanvas({
  site,
  mode = "login",
  fps,
  onClose,
  onSaved,
  onReady,
}: ScreencastCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Decoupled frame render pipeline (React state never touched during frame delivery)
  const latestImageRef = useRef<HTMLImageElement | null>(null);
  const framePendingRef = useRef<boolean>(false);
  const rafIdRef = useRef<number | null>(null);

  // Stream framerate preference state (persists across sessions)
  const [currentFps, setCurrentFps] = useState<number>(() => {
    if (fps) return fps;
    try {
      const saved = sessionStorage.getItem("preferred_stream_fps");
      return saved ? parseInt(saved, 10) : 15;
    } catch {
      return 15;
    }
  });

  // Discrete status states only (launching -> ready -> saving -> saved)
  const [statusText, setStatusText] = useState("Initializing browser session...");
  const [statusState, setStatusState] = useState<string>("launching");
  const [quickText, setQuickText] = useState("");
  const [timeLeft, setTimeLeft] = useState(300);

  // Countdown timer
  useEffect(() => {
    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          toast.error("Browser session timed out (5 minute limit).");
          if (onClose) onClose();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [onClose]);

  const mins = Math.floor(timeLeft / 60);
  const secs = timeLeft % 60;
  const timeFormatted = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;

  // RequestAnimationFrame rendering loop (strictly 0 React re-renders for incoming frames)
  const startRenderLoop = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    const render = () => {
      if (framePendingRef.current && latestImageRef.current && ctx) {
        framePendingRef.current = false;
        try {
          ctx.drawImage(latestImageRef.current, 0, 0, canvas.width, canvas.height);
        } catch {
          // ignore draw glitches
        }
      }
      rafIdRef.current = requestAnimationFrame(render);
    };

    rafIdRef.current = requestAnimationFrame(render);
  }, []);

  useEffect(() => {
    startRenderLoop();
    return () => {
      if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
    };
  }, [startRenderLoop]);

  const retryCountRef = useRef<number>(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isReadyRef = useRef<boolean>(false);
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  // Connect WebSocket via fresh single-use ticket with backoff retry
  const connectSocket = useCallback((force = false) => {
    let isCancelled = false;

    // If already ready or open, do not re-launch or re-connect unless explicitly forced
    if (!force && isReadyRef.current && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      return () => {};
    }

    async function initSocket() {
      if (!isReadyRef.current || force) {
        setStatusText(retryCountRef.current > 0 ? `Reconnecting stream (Attempt ${retryCountRef.current}/3)...` : "Acquiring authentication ticket...");
        setStatusState("launching");
      }

      let ticket = "";
      try {
        const ticketRes = await apiPost<{ ticket: string }>("/api/auth/ws-ticket", {});
        if (ticketRes?.ticket) {
          ticket = ticketRes.ticket;
        }
      } catch (err) {
        console.warn("WS ticket fetch failed, using session auth:", err);
      }

      if (isCancelled) return;

      if (!isReadyRef.current || force) {
        setStatusText("Starting Chromium browser session...");
      }
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ticketParam = ticket ? `ticket=${encodeURIComponent(ticket)}&` : "";
      const wsUrl = `${proto}//${window.location.host}/ws/session/${site}?${ticketParam}mode=${encodeURIComponent(mode)}&fps=${currentFps}`;

      const ws = new WebSocket(wsUrl);
      if (wsRef.current) {
        try {
          wsRef.current.close(1000, "Superseded");
        } catch {
          // ignore
        }
      }
      wsRef.current = ws;

      ws.onopen = () => {
        if (isCancelled || wsRef.current !== ws) return;
        retryCountRef.current = 0; // Reset retry counter upon successful open
      };

      ws.onmessage = (event) => {
        if (isCancelled || wsRef.current !== ws) return;
        try {
          const msg = JSON.parse(event.data);

          if (msg.type === "status") {
            setStatusText(msg.message);
            setStatusState(msg.status || "info");

            if (msg.fps && typeof msg.fps === "number") {
              setCurrentFps(msg.fps);
            }

            if (msg.status === "ready") {
              isReadyRef.current = true;
              if (onReadyRef.current) onReadyRef.current();
            } else if (msg.status === "saved") {
              toast.success(msg.message);
              if (onSavedRef.current) onSavedRef.current();
            } else if (msg.status === "access_denied") {
              toast.error(msg.message, { duration: 8000 });
            } else if (msg.status === "warning") {
              toast.warning(msg.message);
            } else if (msg.status === "fps_updated") {
              toast.info(msg.message || `Stream rate updated to ${msg.fps} FPS`);
            }
          } else if (msg.type === "frame") {
            // Buffer incoming frame into offscreen Image (no setState)
            const img = new Image();
            img.onload = () => {
              latestImageRef.current = img;
              framePendingRef.current = true;
            };
            img.src = "data:image/jpeg;base64," + msg.data;
          } else if (msg.type === "error") {
            setStatusText(`Error: ${msg.message}`);
            setStatusState("error");
            toast.error(msg.message);
          }
        } catch (err) {
          console.error("WebSocket message decode error:", err);
        }
      };

      ws.onerror = (err) => {
        if (isCancelled || wsRef.current !== ws) return;
        console.warn("WebSocket stream error event:", err);
      };

      ws.onclose = (event) => {
        if (isCancelled || wsRef.current !== ws) return;
        isReadyRef.current = false;

        // Auto-reconnect with backoff if disconnected unexpectedly within first few attempts
        if (event.code !== 1000 && retryCountRef.current < 2) {
          retryCountRef.current += 1;
          const delay = retryCountRef.current * 1000;
          setStatusText(`Connection lost (Code: ${event.code}). Retrying in ${delay / 1000}s...`);
          reconnectTimeoutRef.current = setTimeout(() => {
            if (!isCancelled) connectSocket(true);
          }, delay);
          return;
        }

        const reasonText = event.reason ? `: ${event.reason}` : "";
        setStatusText(`Stream disconnected (Code: ${event.code}${reasonText}).`);
        setStatusState("disconnected");
      };
    }

    initSocket();

    return () => {
      isCancelled = true;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      const ws = wsRef.current;
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        try {
          ws.send(JSON.stringify({ type: "cancel" }));
        } catch {
          // ignore
        }
        ws.close(1000, "Client unmount");
      }
    };
  }, [site, mode]);

  useEffect(() => {
    isReadyRef.current = false;
    const cleanup = connectSocket();
    return () => {
      isReadyRef.current = false;
      if (cleanup) cleanup();
    };
  }, [site, mode, connectSocket]);

  // Mouse interaction forwarder
  const sendMouse = (evtName: string, e: React.MouseEvent<HTMLCanvasElement>, clickCount = 1) => {
    const ws = wsRef.current;
    const canvas = canvasRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !canvas) return;

    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = Math.round((e.clientX - rect.left) * scaleX);
    const y = Math.round((e.clientY - rect.top) * scaleY);

    let button = "none";
    if (e.button === 0) button = "left";
    else if (e.button === 1) button = "middle";
    else if (e.button === 2) button = "right";

    ws.send(
      JSON.stringify({
        type: "mouse",
        event: evtName,
        x,
        y,
        button,
        clickCount,
      })
    );
  };

  const sendWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(
      JSON.stringify({
        type: "mouse",
        event: "wheel",
        deltaX: e.deltaX,
        deltaY: e.deltaY,
      })
    );
  };

  // ─── STRICT SINGLE-PATH KEYBOARD INPUT DISPATCH (ZERO DOUBLE TYPING) ───
  const handleCanvasKeyDown = (e: React.KeyboardEvent<HTMLCanvasElement>) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    // 1. Control / Navigation / Editing Keys (Non-printable)
    const isControlKey = [
      "Backspace", "Enter", "Tab", "Escape", "Delete",
      "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
      "Home", "End", "PageUp", "PageDown"
    ].includes(e.key);

    if (isControlKey) {
      e.preventDefault();
      ws.send(JSON.stringify({
        type: "key",
        event: "keyDown",
        key: e.key,
        code: e.code,
        keyCode: e.keyCode
      }));
      return;
    }

    // 2. Ignore pure modifier presses (Shift, Ctrl, Alt, Meta)
    if (["Shift", "Control", "Alt", "Meta", "CapsLock"].includes(e.key)) {
      return;
    }

    // 3. Handle Keyboard Shortcuts (e.g. Ctrl+V, Ctrl+A, Ctrl+C)
    if (e.ctrlKey || e.metaKey) {
      // Let standard browser shortcuts handle paste/copy
      return;
    }

    // 4. Printable Characters (Strictly single path via type_text / insertText ONLY)
    if (e.key.length === 1) {
      e.preventDefault();
      ws.send(JSON.stringify({
        type: "type_text",
        text: e.key
      }));
    }
  };

  const handleCanvasKeyUp = (e: React.KeyboardEvent<HTMLCanvasElement>) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    const isControlKey = [
      "Backspace", "Enter", "Tab", "Escape", "Delete",
      "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"
    ].includes(e.key);

    if (isControlKey) {
      ws.send(JSON.stringify({
        type: "key",
        event: "keyUp",
        key: e.key,
        code: e.code,
        keyCode: e.keyCode
      }));
    }
  };

  const handleCanvasPaste = (e: React.ClipboardEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const text = e.clipboardData.getData("text");
    if (text) {
      ws.send(JSON.stringify({ type: "type_text", text }));
    }
  };

  const sendQuickText = () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !quickText) return;
    ws.send(JSON.stringify({ type: "type_text", text: quickText }));
    setQuickText("");
  };

  const sendKey = (keyName: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "key", event: "keyDown", key: keyName, code: keyName }));
    setTimeout(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "key", event: "keyUp", key: keyName, code: keyName }));
      }
    }, 40);
  };

  const handleFpsChange = (newFps: number) => {
    setCurrentFps(newFps);
    try {
      sessionStorage.setItem("preferred_stream_fps", String(newFps));
    } catch {
      // ignore
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "set_fps", fps: newFps }));
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-950 rounded-2xl border border-slate-800 overflow-hidden shadow-xl">
      {/* Stream Top Control Header */}
      <div className="flex items-center justify-between border-b border-slate-800/80 bg-slate-900/90 px-3.5 py-2">
        <div className="flex items-center gap-2">
          <Monitor className="h-4 w-4 text-emerald-400" />
          <span className="text-xs font-bold font-mono text-foreground uppercase tracking-wider">
            {site} · {mode === "live_check" ? "Live Inspection" : "Browser Login"}
          </span>
          <span
            className={cn(
              "text-[10px] font-mono px-2 py-0.5 rounded font-bold uppercase",
              statusState === "saved"
                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                : statusState === "ready"
                ? "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                : statusState === "access_denied"
                ? "bg-rose-500/20 text-rose-400 border border-rose-500/30 animate-pulse"
                : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
            )}
          >
            {statusState}
          </span>
        </div>

        <div className="flex items-center gap-2 sm:gap-2.5">
          {/* Live Stream Framerate Selector */}
          <div className="flex items-center gap-1 bg-slate-950/90 border border-slate-800 rounded-lg px-2 py-0.5 shadow-xs">
            <span className="text-[10px] text-slate-400 font-mono">FPS:</span>
            <select
              value={currentFps}
              onChange={(e) => handleFpsChange(parseInt(e.target.value, 10))}
              className="bg-transparent text-emerald-400 text-[11px] font-mono font-bold focus:outline-none cursor-pointer"
              title="Stream Delivery Framerate"
            >
              <option value={5} className="bg-slate-950 text-slate-200">5 FPS (Eco)</option>
              <option value={10} className="bg-slate-950 text-slate-200">10 FPS</option>
              <option value={15} className="bg-slate-950 text-slate-200">15 FPS (Default)</option>
              <option value={20} className="bg-slate-950 text-slate-200">20 FPS</option>
              <option value={24} className="bg-slate-950 text-slate-200">24 FPS</option>
              <option value={30} className="bg-slate-950 text-slate-200">30 FPS (Smooth)</option>
              <option value={60} className="bg-slate-950 text-slate-200">60 FPS (Ultra)</option>
            </select>
          </div>

          <span className="text-[11px] font-mono text-amber-400 font-bold">{timeFormatted}</span>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="app-press grid h-6 w-6 place-items-center rounded-lg border border-border text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Access Denied Alert Banner */}
      {statusState === "access_denied" && (
        <div className="bg-rose-500/15 border-b border-rose-500/30 px-3 py-2 flex items-center gap-2 text-rose-300 text-xs">
          <ShieldAlert className="h-4 w-4 shrink-0 text-rose-400" />
          <span className="flex-1">
            <strong>Access Denied by {site === "naukri" ? "Naukri" : "LinkedIn"}:</strong>{" "}
            {statusText || "Anti-bot shield or expired session detected. Live Login se session refresh karo ya session JSON import karo."}
          </span>
        </div>
      )}

      {/* Status Bar */}
      <div className="px-3 py-1.5 bg-muted/30 border-b border-border flex items-center justify-between text-[11px] font-mono text-muted-foreground">
        <span className="truncate">{statusText}</span>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded font-mono font-medium">
            {currentFps} FPS
          </span>
          {(statusState === "disconnected" || statusState === "error") && (
            <button
              type="button"
              onClick={() => {
                retryCountRef.current = 0;
                connectSocket();
              }}
              className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[10px] hover:bg-emerald-500/30 font-sans"
            >
              Reconnect
            </button>
          )}
          <span className="hidden sm:inline text-[10px] text-muted-foreground/70">
            Click canvas to type directly (no duplicate text)
          </span>
        </div>
      </div>

      {/* Screencast Canvas Area */}
      <div className="flex-1 min-h-0 bg-black flex items-center justify-center p-2 overflow-hidden">
        <canvas
          ref={canvasRef}
          width={1280}
          height={800}
          tabIndex={0}
          onMouseDown={(e) => {
            canvasRef.current?.focus();
            sendMouse("mousePressed", e);
          }}
          onMouseUp={(e) => sendMouse("mouseReleased", e)}
          onMouseMove={(e) => sendMouse("mouseMoved", e)}
          onWheel={sendWheel}
          onKeyDown={handleCanvasKeyDown}
          onKeyUp={handleCanvasKeyUp}
          onPaste={handleCanvasPaste}
          className="max-h-full max-w-full object-contain border border-border/50 rounded cursor-crosshair outline-none focus:border-emerald-500/70 transition-colors shadow-2xl"
        />
      </div>

      {/* Remote Interaction & Quick Input Bar */}
      <div className="border-t border-border bg-card/90 p-2.5 flex flex-wrap items-center gap-1.5">
        <div className="flex-1 min-w-[200px] flex items-center gap-1.5">
          <input
            type="text"
            value={quickText}
            onChange={(e) => setQuickText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                sendQuickText();
              }
            }}
            placeholder="Type or paste text (email / password / OTP)..."
            className="h-8 flex-1 rounded-lg border border-border bg-background px-2.5 text-xs font-mono text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-emerald-500/50"
          />
          <button
            type="button"
            onClick={sendQuickText}
            className="h-8 px-3 rounded-lg border border-emerald-500/35 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 text-xs font-semibold flex items-center gap-1 app-press cursor-pointer"
          >
            <Send className="h-3 w-3" />
            <span>Send</span>
          </button>
        </div>

        {/* Remote key helpers */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => sendKey("Enter")}
            className="h-8 px-2.5 rounded-lg border border-border bg-card hover:bg-muted text-xs font-mono text-foreground flex items-center gap-1 app-press cursor-pointer"
          >
            <CornerDownLeft className="h-3 w-3" />
            <span>Enter</span>
          </button>
          <button
            type="button"
            onClick={() => sendKey("Tab")}
            className="h-8 px-2.5 rounded-lg border border-border bg-card hover:bg-muted text-xs font-mono text-foreground flex items-center gap-1 app-press cursor-pointer"
          >
            <ArrowRightToLine className="h-3 w-3" />
            <span>Tab</span>
          </button>
          <button
            type="button"
            onClick={() => sendKey("Backspace")}
            className="h-8 px-2.5 rounded-lg border border-border bg-card hover:bg-muted text-xs font-mono text-foreground flex items-center gap-1 app-press cursor-pointer"
          >
            <Delete className="h-3 w-3" />
            <span>Bksp</span>
          </button>
        </div>
      </div>
    </div>
  );
}
