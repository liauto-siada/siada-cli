import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      gridTemplateColumns: {
        "20": "repeat(20, minmax(0, 1fr))",
      },
      gridTemplateRows: {
        "20": "repeat(20, minmax(0, 1fr))",
      },
    },
  },
  darkMode: ["class", "media"],
};

export default config;
