/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "#090a0f",
        surface: "#12131a",
        surfaceBorder: "#1f2230",
        accent: {
          DEFAULT: "#6366f1",
          hover: "#4f46e5",
          glow: "rgba(99, 102, 241, 0.25)",
        }
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
      }
    },
  },
  plugins: [],
}
