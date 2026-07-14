import { useEffect, useState } from "react";

const STORAGE_KEY = "theme";

function getInitialIsDark(): boolean {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "dark") return true;
  if (stored === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/**
 * Tailwind here is configured with darkMode: "class" (tailwind.config.js),
 * meaning every dark: variant styled throughout the app only ever activates
 * when something adds a "dark" class to <html> -- nothing did, so dark mode
 * was unreachable dead code until this hook existed.
 */
export function useDarkMode(): [boolean, () => void] {
  const [isDark, setIsDark] = useState(getInitialIsDark);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
    localStorage.setItem(STORAGE_KEY, isDark ? "dark" : "light");
  }, [isDark]);

  return [isDark, () => setIsDark((v) => !v)];
}
