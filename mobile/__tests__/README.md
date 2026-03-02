# FormCheck Mobile Testing Framework

This directory contains the comprehensive testing suite for the FormCheck mobile application.

## Overview

The testing framework uses:
- **Jest** - JavaScript testing framework
- **React Native Testing Library** - Component testing utilities
- **jest-expo** - Expo-specific Jest preset

## Test Structure

```
__tests__/
├── setup.ts                    # Global test configuration and mocks
├── utils/                      # Testing utilities
│   ├── testHelpers.ts         # Common helper functions
│   └── mockData.ts            # Mock data factories
├── lib/                       # Library tests
│   ├── api.test.ts           # API client tests
│   └── supabase.test.ts      # Supabase client tests
└── components/                # Component tests
    ├── ShotMarkerTimeline.test.tsx
    └── RimCalibrationOverlay.test.tsx
```

## Running Tests

### Run all tests
```bash
npm test
```

### Run tests in watch mode
```bash
npm run test:watch
```

### Run tests with coverage
```bash
npm run test:coverage
```

### Run specific test file
```bash
npm test api.test.ts
```

### Run tests matching a pattern
```bash
npm test -- --testNamePattern="fetchWithTimeout"
```

## Test Coverage

Current coverage targets (configured in jest.config.js):
- Statements: 70%
- Branches: 60%
- Functions: 70%
- Lines: 70%

View coverage report after running `npm run test:coverage` in the `coverage/` directory.

## Writing Tests

### Test Structure (Arrange-Act-Assert)

```typescript
it('should do something', () => {
  // Arrange - Set up test data and mocks
  const mockData = createMockSessionSummary();
  mockFetch(createMockResponse(mockData));

  // Act - Execute the code under test
  const result = await analyzeVideo('test.mp4');

  // Assert - Verify the results
  expect(result).toEqual(mockData);
});
```

### Using Mock Data Factories

Mock data factories are available in `__tests__/utils/mockData.ts`:

```typescript
import {
  createMockShotAnalysis,
  createMockSessionSummary,
  createMockProfile,
  createMockSession,
} from '../utils/mockData';

const shot = createMockShotAnalysis({ made: true, timestamp: 5.0 });
const session = createMockSession({ shot_count: 10 });
```

### Mocking Fetch Requests

Use the test helpers to mock API responses:

```typescript
import { mockFetch, createMockResponse } from '../utils/testHelpers';

mockFetch(createMockResponse({ status: 'ok' }));

// Or for errors
mockFetch(createMockErrorResponse(404, 'Not found'));
```

### Testing Components

```typescript
import { render, fireEvent } from '@testing-library/react-native';

it('should render component', () => {
  const { getByText } = render(<MyComponent />);

  expect(getByText('Hello')).toBeTruthy();
});

it('should handle button press', () => {
  const onPress = jest.fn();
  const { getByText } = render(<Button onPress={onPress} />);

  fireEvent.press(getByText('Click me'));

  expect(onPress).toHaveBeenCalled();
});
```

## Test Files

### API Client Tests (`lib/api.test.ts`)

Tests for the FormCheck API client:
- ✅ `fetchWithTimeout` - timeout handling, successful requests
- ✅ `handleResponse` - JSON parsing, error extraction
- ✅ `testConnection` - health check logic
- ✅ `analyzeVideo` - FormData construction, query params, error handling
- ✅ `getHealthStatus` - health status retrieval
- ✅ `getApiInfo` - API info retrieval

**Key test cases:**
- Successful API calls
- Timeout handling
- Error response parsing
- Query parameter construction
- FormData file upload
- Error message transformation

### Supabase Client Tests (`lib/supabase.test.ts`)

Tests for the Supabase database client:
- ✅ Profile operations - get, update
- ✅ Session operations - get, create, update, delete
- ✅ Shot operations - get, create batch
- ✅ Stats calculations - user stats, aggregation
- ✅ Storage operations - thumbnail upload
- ✅ Utility functions - configuration check, user ID

**Key test cases:**
- Database CRUD operations
- Authentication checks
- Stats aggregation logic
- Error handling
- Pagination

### ShotMarkerTimeline Tests (`components/ShotMarkerTimeline.test.tsx`)

Tests for the shot marker timeline component:
- ✅ Rendering - empty states, multiple shots
- ✅ Marker positioning - start, middle, end, clamping
- ✅ Marker colors - made (green), missed (red), unknown (gray)
- ✅ Seek behavior - timestamp calculation, pre-shot offset
- ✅ Edge cases - single shot, many shots, same timestamps

**Key test cases:**
- Position calculation (percentage of timeline)
- Color based on shot result
- Seek with 1.5s pre-shot offset
- Boundary clamping

### RimCalibrationOverlay Tests (`components/RimCalibrationOverlay.test.tsx`)

Tests for the rim calibration overlay component:
- ✅ Rendering - initial state, video display, instructions
- ✅ Tap coordinate normalization - 0-1 range, clamping
- ✅ State management - position setting, reset
- ✅ Button callbacks - confirm, skip, rim not visible, change video
- ✅ Edge cases - multiple taps, precision, zero coordinates
- ✅ Integration - complete flows

**Key test cases:**
- Coordinate normalization to 0-1 range
- Boundary clamping
- State transitions
- Callback invocation with correct parameters

## Mocking Strategy

### Global Mocks (setup.ts)

The following are mocked globally for all tests:
- AsyncStorage
- Expo modules (constants, video, vector-icons)
- React Native Reanimated
- Gesture Handler

### Per-Test Mocks

API and Supabase clients are mocked in individual test files to allow fine-grained control over test scenarios.

## Best Practices

1. **Use descriptive test names** - Test names should clearly describe what is being tested
2. **Test one thing at a time** - Each test should verify a single behavior
3. **Mock external dependencies** - Don't make real API calls or database queries
4. **Clean up after tests** - Use `beforeEach` and `afterEach` to reset state
5. **Test edge cases** - Include tests for error conditions, empty states, boundary values
6. **Avoid implementation details** - Test behavior, not implementation
7. **Keep tests fast** - Use mocks to avoid slow operations
8. **Maintain tests** - Update tests when code changes

## Troubleshooting

### Tests failing with "Cannot find module"
- Check that all imports are correct
- Verify transformIgnorePatterns in jest.config.js includes the module

### Tests timing out
- Check for missing mock implementations
- Ensure async operations are properly awaited
- Increase timeout with `jest.setTimeout()`

### React Native component not rendering
- Verify component mocks in setup.ts
- Check that @testing-library/react-native is properly configured

### Fetch not working in tests
- Ensure global.fetch is mocked before use
- Use mockFetch helper from testHelpers.ts

## CI/CD Integration

To run tests in CI/CD:

```yaml
- name: Run tests
  run: npm test -- --ci --coverage --maxWorkers=2
```

The `--ci` flag optimizes Jest for CI environments.

## Future Improvements

- [ ] Add integration tests for complete user flows
- [ ] Add snapshot testing for complex components
- [ ] Add performance testing for video analysis
- [ ] Add E2E tests with Detox
- [ ] Increase coverage to 80%+
- [ ] Add visual regression testing
