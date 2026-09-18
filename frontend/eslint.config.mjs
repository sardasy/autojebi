import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      ".next/**",
      "**/.next/**",
      "**/.next-*/**",
      "coverage/**",
      "**/coverage/**",
      "node_modules/**",
      "**/node_modules/**",
      "out/**",
      "**/out/**",
      "playwright-report/**",
      "**/playwright-report/**",
      "test-results/**",
      "**/test-results/**",
    ],
  },
  {
    linterOptions: {
      reportUnusedDisableDirectives: false,
    },
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.js", "**/*.cjs", "**/*.mjs"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "commonjs",
      globals: {
        ...globals.es2022,
        ...globals.node,
      },
    },
    rules: {
      "@typescript-eslint/no-require-imports": "off",
    },
  },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.es2022,
        ...globals.node,
      },
    },
    rules: {
      "@typescript-eslint/no-empty-object-type": "off",
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
        },
      ],
      "no-empty": ["error", { allowEmptyCatch: true }],
    },
  },
  {
    files: [
      "**/*.test.{ts,tsx}",
      "e2e/**/*.ts",
      "src/components/__tests__/**/*.{ts,tsx}",
      "test/**/*.ts",
    ],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.es2022,
        ...globals.node,
        ...globals.vitest,
      },
    },
  },
  {
    // ADR 0001 FF 5: UI code reaches the backend only through lib clients
    // (lib/workspace: workspaceFetch/workspaceApi/workspaceSessionFetch, lib/api for v1).
    files: ["src/components/**/*.{ts,tsx}", "src/app/**/*.{ts,tsx}"],
    ignores: ["src/**/__tests__/**", "src/app/api/**"],
    rules: {
      "no-restricted-globals": ["error", {
        name: "fetch",
        message: "Use workspaceFetch/workspaceApi from @/lib/workspace (or lib/api for v1). ADR 0001.",
      }],
    },
  },
  {
    files: ["next-env.d.ts"],
    rules: {
      "@typescript-eslint/triple-slash-reference": "off",
    },
  },
);
