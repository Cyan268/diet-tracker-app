module.exports = {
  preset: "jest-expo",
  transformIgnorePatterns: [
    "node_modules/(?!((jest-)?react-native|@react-native(-community)?)|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@sentry/react-native|native-base|react-native-svg|uuid)",
  ],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  collectCoverageFrom: [
    "src/features/**/*.{ts,tsx}",
    "src/services/**/*.{ts,tsx}",
    "!src/**/*.d.ts",
  ],
  coverageDirectory: "coverage",
};
