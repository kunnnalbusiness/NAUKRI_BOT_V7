import { useEffect, useRef } from "react";

export function useScrollRestoration<T extends HTMLElement>(key: string) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Restore scroll position
    const saved = sessionStorage.getItem(`scroll_${key}`);
    if (saved) {
      el.scrollTop = parseInt(saved, 10);
    }

    // Save on scroll
    const handleScroll = () => {
      sessionStorage.setItem(`scroll_${key}`, el.scrollTop.toString());
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      el.removeEventListener("scroll", handleScroll);
    };
  }, [key]);

  return ref;
}
