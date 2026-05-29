// Light/dark theme toggle. Author: Al Amin Ahamed.
import { Moon, Sun } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { type Theme, getTheme, setTheme } from "@/lib/config";

export function ThemeToggle() {
  const [theme, setLocal] = useState<Theme>(getTheme());
  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    setLocal(next);
  }
  return (
    <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
      {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}
