import React from "react";
import { Link } from "react-router-dom";
import { Bot } from "lucide-react";

interface TopBarProps {
  title: string;
  left?: React.ReactNode;
  right?: React.ReactNode;
}

export default function TopBar({ title, left, right }: TopBarProps) {
  return (
    <div className="flex h-12 w-full items-center justify-between border-b border-border bg-background/95 px-3 backdrop-blur-md">
      <div className="flex items-center gap-2">
        {left ? (
          left
        ) : (
          <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
            <Bot className="h-4 w-4" />
          </div>
        )}
        <h1 className="font-heading text-sm font-bold text-foreground tracking-tight">{title}</h1>
      </div>
      {right ? <div className="flex items-center gap-1.5">{right}</div> : null}
    </div>
  );
}
