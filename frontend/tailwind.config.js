/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        risk: {
          critical: "#b91c1c",
          high: "#c2410c",
          medium: "#a16207",
          low: "#15803d",
        },
      },
    },
  },
  plugins: [],
};
