<template>
  <router-view />
</template>

<script setup>
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

:root {
  color-scheme: light dark;
  --deep-blue: #122E8A;
  --off-white: #F1DDDF;
  --bg-primary: var(--off-white);
  --bg-secondary: #FFFFFF;
  --text-primary: var(--deep-blue);
  --text-secondary: #4A5A8A;
  --accent: var(--deep-blue);
  --accent-light: #1E4AB0;
  --accent-strong: #0D1F6B;
  --glass-bg: rgba(255, 255, 255, 0.25);
  --glass-border: rgba(255, 255, 255, 0.4);
  --glass-shadow: rgba(18, 46, 138, 0.08);
  --card-shadow: rgba(18, 46, 138, 0.06);
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg-primary: #0A1628;
    --bg-secondary: #122040;
    --text-primary: #F1DDDF;
    --text-secondary: #A0B0D0;
    --glass-bg: rgba(18, 32, 64, 0.6);
    --glass-border: rgba(241, 221, 223, 0.15);
    --glass-shadow: rgba(0, 0, 0, 0.3);
    --card-shadow: rgba(0, 0, 0, 0.2);
  }
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans SC', system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background: var(--bg-primary);
  color: var(--text-primary);
  transition: background 0.4s ease, color 0.4s ease;
  min-height: 100vh;
  overflow-x: hidden;
}

#app {
  min-height: 100vh;
}

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--deep-blue); border-radius: 3px; opacity: 0.5; }
::-webkit-scrollbar-thumb:hover { background: var(--accent-light); }
button { font-family: inherit; cursor: pointer; }
a { color: inherit; text-decoration: none; }
</style>
