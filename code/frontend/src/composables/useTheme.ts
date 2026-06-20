import { ref, watchEffect } from "vue";

export type ThemeName = "light" | "dark";

const LS_KEY = "emedicine.theme";

function detect(): ThemeName {
  const saved = localStorage.getItem(LS_KEY);
  if (saved === "light" || saved === "dark") return saved;
  // Preferinta sistemului ca default
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return "light";
}

// Stare globala (singura instanta in toata aplicatia)
const theme = ref<ThemeName>(detect());

watchEffect(() => {
  document.documentElement.setAttribute("data-theme", theme.value);
  localStorage.setItem(LS_KEY, theme.value);
});

export function useTheme() {
  function toggle() {
    theme.value = theme.value === "light" ? "dark" : "light";
  }
  function setTheme(t: ThemeName) {
    theme.value = t;
  }
  return { theme, toggle, setTheme };
}
