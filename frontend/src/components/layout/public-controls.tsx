import { useState } from "react";
import { Link } from "react-router-dom";
import { Layers3, Moon, Pause, Play, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/lib/theme";

export function PublicWordmark(): JSX.Element {
  return (
    <Link to="/" className="public-wordmark" aria-label="EPOS home">
      <span className="public-brand-icon" aria-hidden="true"><Layers3 size={21} strokeWidth={1.6} /></span>
      <span>EPOS</span>
    </Link>
  );
}

export function PublicThemeToggle(): JSX.Element {
  const { theme, toggle } = useTheme();
  return <Button variant="ghost" className="icon-button" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
    {theme === "dark" ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
  </Button>;
}

export function useBackgroundMotion(): { paused: boolean; control: JSX.Element } {
  const [paused, setPaused] = useState(false);
  return {
    paused,
    control: <Button variant="ghost" className="public-motion-control" onClick={() => setPaused(value => !value)} aria-label={paused ? "Resume background animation" : "Pause background animation"}>
      {paused ? <Play size={13} aria-hidden="true" /> : <Pause size={13} aria-hidden="true" />}
      <span>{paused ? "Resume motion" : "Pause motion"}</span>
    </Button>,
  };
}