/**
 * Test Helpers
 * Common utility functions for testing
 */

/**
 * Wait for async operations to complete
 */
export const waitFor = (ms: number): Promise<void> => {
  return new Promise(resolve => setTimeout(resolve, ms));
};

/**
 * Create a mock fetch response
 */
export const createMockResponse = <T>(
  data: T,
  options: {
    status?: number;
    ok?: boolean;
    statusText?: string;
  } = {}
): Response => {
  const {
    status = 200,
    ok = true,
    statusText = 'OK',
  } = options;

  return {
    ok,
    status,
    statusText,
    json: jest.fn().mockResolvedValue(data),
    text: jest.fn().mockResolvedValue(JSON.stringify(data)),
    headers: new Headers(),
    redirected: false,
    type: 'basic',
    url: '',
    clone: jest.fn(),
    body: null,
    bodyUsed: false,
    arrayBuffer: jest.fn(),
    blob: jest.fn(),
    formData: jest.fn(),
  } as unknown as Response;
};

/**
 * Create a mock fetch error response
 */
export const createMockErrorResponse = (
  statusCode: number,
  errorMessage: string
): Response => {
  return {
    ok: false,
    status: statusCode,
    statusText: 'Error',
    json: jest.fn().mockResolvedValue({ detail: errorMessage }),
    text: jest.fn().mockResolvedValue(errorMessage),
    headers: new Headers(),
    redirected: false,
    type: 'basic',
    url: '',
    clone: jest.fn(),
    body: null,
    bodyUsed: false,
    arrayBuffer: jest.fn(),
    blob: jest.fn(),
    formData: jest.fn(),
  } as unknown as Response;
};

/**
 * Mock global fetch
 */
export const mockFetch = (response: Response | Promise<Response>) => {
  global.fetch = jest.fn().mockResolvedValue(response);
  return global.fetch as jest.MockedFunction<typeof fetch>;
};

/**
 * Clear all mocks
 */
export const clearAllMocks = () => {
  jest.clearAllMocks();
};
