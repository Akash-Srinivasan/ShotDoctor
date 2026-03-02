/**
 * Setup before Jest environment is initialized
 * This runs before any modules are imported
 */

// Mock Expo's winter runtime
global.__ExpoImportMetaRegistry = {};
global.structuredClone = global.structuredClone || (obj => JSON.parse(JSON.stringify(obj)));

// Required for React Native new architecture
jest.mock('react-native/Libraries/TurboModule/TurboModuleRegistry', () => ({
  getEnforcing: () => ({}),
  get: () => ({}),
}));
