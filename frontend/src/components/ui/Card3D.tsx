import React, { useRef, useState } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { cn } from "@/lib/utils";

interface Card3DProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  className?: string;
  depth?: number;
  glowColor?: string;
  enableGlow?: boolean;
}

export default function Card3D({
  children,
  className,
  depth = 12,
  glowColor = "rgba(16, 185, 129, 0.15)",
  enableGlow = true,
  ...props
}: Card3DProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [isHovered, setIsHovered] = useState(false);

  // Raw mouse coordinates relative to center of card (-0.5 to 0.5)
  const x = useMotionValue(0);
  const y = useMotionValue(0);

  // Smooth physics-based spring transforms
  const springConfig = { damping: 20, stiffness: 260 };
  const rotateX = useSpring(useTransform(y, [-0.5, 0.5], [depth, -depth]), springConfig);
  const rotateY = useSpring(useTransform(x, [-0.5, 0.5], [-depth, depth]), springConfig);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const xPct = mouseX / rect.width - 0.5;
    const yPct = mouseY / rect.height - 0.5;
    x.set(xPct);
    y.set(yPct);
  };

  const handleMouseEnter = () => {
    setIsHovered(true);
  };

  const handleMouseLeave = () => {
    setIsHovered(false);
    x.set(0);
    y.set(0);
  };

  return (
    <div
      ref={ref}
      onMouseMove={handleMouseMove}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      style={{ perspective: 1200 }}
      className="relative select-none"
    >
      <motion.div
        style={{
          rotateX,
          rotateY,
          transformStyle: "preserve-3d",
        }}
        animate={{
          scale: isHovered ? 1.015 : 1,
        }}
        transition={{ duration: 0.2 }}
        className={cn(
          "relative rounded-xl border border-border/80 bg-card/90 p-4 transition-colors duration-300 backdrop-blur-xl",
          "hover:border-emerald-500/40 hover:shadow-[0_12px_40px_-10px_rgba(0,0,0,0.8)]",
          className
        )}
        {...(props as any)}
      >
        {/* Specular dynamic light sweep on hover */}
        {enableGlow && isHovered && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="pointer-events-none absolute -inset-px rounded-xl opacity-60 transition-opacity duration-300"
            style={{
              background: `radial-gradient(400px circle at calc(50% + ${x.get() * 300}px) calc(50% + ${y.get() * 300}px), ${glowColor}, transparent 70%)`,
            }}
          />
        )}

        <div style={{ transform: "translateZ(20px)", transformStyle: "preserve-3d" }}>
          {children}
        </div>
      </motion.div>
    </div>
  );
}
