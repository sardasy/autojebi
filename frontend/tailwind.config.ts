import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#fef2f2",
          500: "#dc2626",
          600: "#b91c1c",
          700: "#991b1b",
        },
      },
    },
  },
  plugins: [],
};
export default config;
