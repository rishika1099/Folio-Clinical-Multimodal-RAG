/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'Inter'", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
        display: ["'Space Grotesk'", "'Inter'", "sans-serif"],
      },
      colors: {
        // Pastel light palette. Names preserved (ink-50 = primary text,
        // ink-950 = page bg) so existing classes flip semantically clean.
        ink: {
          50:  "#1c1f2a",   // headings
          100: "#272a36",   // primary text
          150: "#363a48",
          200: "#4d5263",   // secondary text
          300: "#6b7184",   // muted text
          400: "#8d92a3",   // faint
          500: "#aeb2c0",
          600: "#cfd2dc",   // border-2
          700: "#e0e3eb",   // border default
          800: "#ecedf2",   // hover surface
          850: "#f3f2ed",   // raised cream
          900: "#f7f5ef",   // surface secondary
          950: "#fbf9f3",   // page bg (warm cream)
        },
        surface: "#ffffff",
        // Pastel accents.
        accent: {
          DEFAULT: "#7aaba5",   // sage teal — primary
          soft:    "#d8ebe7",
          softer:  "#eaf3f1",
          deep:    "#4f8a83",
          ink:     "#2a4f4a",
        },
        warn: {
          DEFAULT: "#e1a06e",   // peach
          soft:    "#fbe5d2",
          softer:  "#fcf1e6",
          deep:    "#a36a3f",
          ink:     "#5e3a1c",
        },
        alert: {
          DEFAULT: "#d68888",   // dusty rose
          soft:    "#f7dcdc",
          softer:  "#fbeded",
          deep:    "#a35858",
          ink:     "#5e2828",
        },
        good: {
          DEFAULT: "#83bf9e",   // mint sage
          soft:    "#dcefe2",
          softer:  "#ecf5ee",
          deep:    "#508a6a",
          ink:     "#244e35",
        },
        info: {
          DEFAULT: "#9c91c0",   // soft lavender
          soft:    "#e5e0f0",
          softer:  "#efecf6",
          deep:    "#6e6294",
          ink:     "#3a3160",
        },
      },
      boxShadow: {
        glow: "0 1px 0 0 rgba(122,171,165,0.18) inset, 0 8px 24px -10px rgba(122,171,165,0.35)",
        card: "0 1px 1px 0 rgba(28,31,42,0.03), 0 6px 20px -10px rgba(28,31,42,0.10)",
        cardHover: "0 1px 1px 0 rgba(28,31,42,0.04), 0 12px 32px -12px rgba(28,31,42,0.14)",
      },
      backgroundImage: {
        grid: "radial-gradient(circle at 1px 1px, rgba(28,31,42,0.05) 1px, transparent 0)",
      },
      animation: {
        "pulse-soft": "pulseSoft 2.4s ease-in-out infinite",
        "stream": "stream 1.6s linear infinite",
        "float": "float 6s ease-in-out infinite",
        "rise": "rise 480ms cubic-bezier(0.2, 0.8, 0.2, 1) both",
        "rise-out": "riseOut 320ms cubic-bezier(0.4, 0, 0.6, 1) both",
      },
      keyframes: {
        pulseSoft: {
          "0%, 100%": { opacity: "0.6" },
          "50%": { opacity: "1" },
        },
        stream: {
          "0%": { backgroundPosition: "0% 0%" },
          "100%": { backgroundPosition: "200% 0%" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        rise: {
          "0%":   { opacity: "0", transform: "translateY(14px) scale(0.97)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        riseOut: {
          "0%":   { opacity: "1", transform: "translateY(0)" },
          "100%": { opacity: "0", transform: "translateY(-8px)" },
        },
      },
    },
  },
  plugins: [],
};
