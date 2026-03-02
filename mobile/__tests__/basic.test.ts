/**
 * Basic Test
 * Verifies Jest is configured correctly
 */

describe('Basic Test Suite', () => {
  it('should pass a simple test', () => {
    expect(1 + 1).toBe(2);
  });

  it('should have environment variables set', () => {
    expect(process.env.EXPO_PUBLIC_API_URL).toBe('http://localhost:8000');
    expect(process.env.EXPO_PUBLIC_SUPABASE_URL).toBe('https://test.supabase.co');
    expect(process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY).toBe('test-anon-key');
  });

  it('should mock console methods', () => {
    console.log('test');
    expect(console.log).toHaveBeenCalledWith('test');
  });

  it('should handle async operations', async () => {
    const promise = Promise.resolve(42);
    const result = await promise;
    expect(result).toBe(42);
  });
});
