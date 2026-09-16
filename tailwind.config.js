/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        moss: {
          50: "#eaede8",
          100: "#f5f7f4",
          400: "#8fa087",
          500: "#6e8165",
          600: "#475441",
          700: "#2e3429",
        },
        gold: {
          400: "#d4b06a",
          500: "#c9973a",
          600: "#9a6e22",
        },
        line: "#d4dbd1",
      },
      fontFamily: {
        cinzel: ["'Cinzel'", "serif"],
        "cinzel-deco": ["'Cinzel Decorative'", "serif"],
        scheherazade: ["'Scheherazade New'", "serif"],
        garamond: ["'EB Garamond'", "serif"],
        outfit: ["'Outfit'", "sans-serif"],
      },
    },
  },
  plugins: [],
};
