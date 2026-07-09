import path from "node:path";
import { fileURLToPath } from "node:url";
import js from "@eslint/js";
import { FlatCompat } from "@eslint/eslintrc";

const root = path.dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({
  baseDirectory: root,
  recommendedConfig: js.configs.recommended,
  allConfig: js.configs.all,
});

const config = [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // Existing API payloads are still incrementally moving from loose provider
      // dictionaries to generated contracts. Keep that migration visible without
      // making the first lint baseline a blanket rewrite.
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
      "react/no-unescaped-entities": "off",
    },
  },
];

export default config;
