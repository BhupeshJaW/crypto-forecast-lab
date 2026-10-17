/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#0c1015", 900: "#10151c", 800: "#171d26", 700: "#232b37", 600: "#334050" },
        fog: { 100: "#e4e8ee", 300: "#aab3c0", 500: "#7b8696" },
        brass: { 400: "#e0a84a", 500: "#c98f2f" },
        up: "#3fb68b",
        down: "#e5645f",
        warn: "#e0a84a",
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
    },
  },
  plugins: [],
};
