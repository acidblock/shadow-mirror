# Playwright Patterns for Shadow Mirror

## Project Structure

```
tests/
├── playwright.config.ts
├── shadows/                    # Trace output directory
├── fixtures/
│   └── shadow-fixture.ts       # Custom instrumentation
└── e2e/
    ├── happy-paths/
    ├── chaos/
    └── visual/
```

## Shadow Fixture

```typescript
// fixtures/shadow-fixture.ts
import { test as base, expect } from '@playwright/test';

type ShadowFixtures = {
  shadowTrace: {
    node: (path: string) => void;
    level: (l: 'functional' | 'behavioral' | 'performant' | 'resilient' | 'observable') => void;
    evidence: (name: string, data: any) => void;
  };
};

export const test = base.extend<ShadowFixtures>({
  shadowTrace: async ({ page }, use, testInfo) => {
    const evidence: any[] = [];
    const metadata = { node: '', level: 'functional' };
    
    await use({
      node: (path: string) => { metadata.node = path; },
      level: (l) => { metadata.level = l; },
      evidence: (name, data) => {
        evidence.push({ name, data, ts: new Date().toISOString() });
      },
    });
    
    // Attach evidence to test report
    await testInfo.attach('shadow-evidence', {
      body: JSON.stringify({ metadata, evidence }, null, 2),
      contentType: 'application/json',
    });
  },
});

export { expect };
```

## Happy Path Validation

```typescript
// e2e/happy-paths/login.spec.ts
import { test, expect } from '../../fixtures/shadow-fixture';

test.describe('Login Flow', () => {
  test('successful login journey', async ({ page, shadowTrace }) => {
    shadowTrace.node('auth.login.happy_path');
    shadowTrace.level('behavioral');
    
    // Step 1: Navigate
    await page.goto('/login');
    shadowTrace.evidence('navigation', { url: '/login', status: 'complete' });
    
    // Step 2: Fill credentials
    await page.fill('[data-testid="email"]', 'user@example.com');
    await page.fill('[data-testid="password"]', 'password123');
    shadowTrace.evidence('form_filled', { fields: ['email', 'password'] });
    
    // Step 3: Submit
    await page.click('[data-testid="submit"]');
    
    // Step 4: Assert destination
    await expect(page).toHaveURL('/dashboard');
    shadowTrace.evidence('redirect', { destination: '/dashboard', success: true });
  });
  
  test('displays validation errors', async ({ page, shadowTrace }) => {
    shadowTrace.node('auth.login.validation');
    shadowTrace.level('functional');
    
    await page.goto('/login');
    await page.click('[data-testid="submit"]');
    
    await expect(page.locator('.error-message')).toBeVisible();
    shadowTrace.evidence('validation', { error_shown: true });
  });
});
```

## Chaos Monkey Patterns

```typescript
// e2e/chaos/network-failures.spec.ts
import { test, expect } from '../../fixtures/shadow-fixture';

test.describe('Resilience under network failure', () => {
  test('handles API timeout gracefully', async ({ page, shadowTrace, context }) => {
    shadowTrace.node('api.resilience.timeout');
    shadowTrace.level('resilient');
    
    // Inject 30s delay on API calls
    await context.route('**/api/**', async (route) => {
      shadowTrace.evidence('route_intercepted', { url: route.request().url() });
      await new Promise(r => setTimeout(r, 30000));
      await route.continue();
    });
    
    await page.goto('/dashboard');
    
    // Should show loading state, not crash
    await expect(page.locator('[data-testid="loading"]')).toBeVisible();
    shadowTrace.evidence('graceful_degradation', { loading_shown: true });
  });
  
  test('recovers from network disconnect', async ({ page, shadowTrace, context }) => {
    shadowTrace.node('api.resilience.disconnect');
    shadowTrace.level('resilient');
    
    await page.goto('/dashboard');
    
    // Simulate network failure
    await context.setOffline(true);
    shadowTrace.evidence('network_offline', { ts: Date.now() });
    
    await page.click('[data-testid="refresh"]');
    await expect(page.locator('[data-testid="offline-banner"]')).toBeVisible();
    
    // Restore network
    await context.setOffline(false);
    shadowTrace.evidence('network_restored', { ts: Date.now() });
    
    await page.click('[data-testid="retry"]');
    await expect(page.locator('[data-testid="content"]')).toBeVisible();
    shadowTrace.evidence('recovery_complete', { success: true });
  });
  
  test('handles partial API response', async ({ page, shadowTrace, context }) => {
    shadowTrace.node('api.resilience.partial_response');
    shadowTrace.level('resilient');
    
    await context.route('**/api/data', async (route) => {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({ items: null }), // Malformed response
      });
    });
    
    await page.goto('/list');
    await expect(page.locator('[data-testid="empty-state"]')).toBeVisible();
    shadowTrace.evidence('handled_malformed', { empty_state_shown: true });
  });
});
```

## Network Interception & API Contract Validation

```typescript
// e2e/happy-paths/api-contracts.spec.ts
import { test, expect } from '../../fixtures/shadow-fixture';

test('API response matches contract', async ({ page, shadowTrace }) => {
  shadowTrace.node('api.contract.users');
  shadowTrace.level('functional');
  
  const responses: any[] = [];
  
  page.on('response', async (response) => {
    if (response.url().includes('/api/users')) {
      const body = await response.json();
      responses.push({
        url: response.url(),
        status: response.status(),
        body,
      });
    }
  });
  
  await page.goto('/users');
  await page.waitForResponse('**/api/users');
  
  // Contract assertions
  expect(responses).toHaveLength(1);
  expect(responses[0].status).toBe(200);
  expect(responses[0].body).toHaveProperty('users');
  expect(Array.isArray(responses[0].body.users)).toBe(true);
  
  shadowTrace.evidence('api_contract', {
    endpoint: '/api/users',
    contract_valid: true,
    response_shape: Object.keys(responses[0].body),
  });
});
```

## Visual Regression

```typescript
// e2e/visual/screenshots.spec.ts
import { test, expect } from '../../fixtures/shadow-fixture';

test.describe('Visual regression', () => {
  test('dashboard matches baseline', async ({ page, shadowTrace }) => {
    shadowTrace.node('ui.visual.dashboard');
    shadowTrace.level('functional');
    
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Full page screenshot comparison
    await expect(page).toHaveScreenshot('dashboard.png', {
      maxDiffPixels: 100,
      threshold: 0.2,
    });
    
    shadowTrace.evidence('visual_comparison', {
      baseline: 'dashboard.png',
      threshold: 0.2,
      passed: true,
    });
  });
  
  test('responsive breakpoints', async ({ page, shadowTrace }) => {
    shadowTrace.node('ui.visual.responsive');
    shadowTrace.level('behavioral');
    
    const breakpoints = [
      { name: 'mobile', width: 375, height: 667 },
      { name: 'tablet', width: 768, height: 1024 },
      { name: 'desktop', width: 1440, height: 900 },
    ];
    
    for (const bp of breakpoints) {
      await page.setViewportSize({ width: bp.width, height: bp.height });
      await page.goto('/dashboard');
      
      await expect(page).toHaveScreenshot(`dashboard-${bp.name}.png`);
      shadowTrace.evidence(`visual_${bp.name}`, { viewport: bp, passed: true });
    }
  });
});
```

## Trace Configuration

```typescript
// playwright.config.ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  outputDir: './tests/shadows',
  
  use: {
    trace: 'on',  // Always capture traces for shadow evidence
    screenshot: 'on',
    video: 'retain-on-failure',
  },
  
  reporter: [
    ['html', { outputFolder: 'shadow-report/playwright' }],
    ['json', { outputFile: 'shadow-report/playwright.json' }],
  ],
  
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
});
```

## HAR Recording for Network Evidence

```typescript
test('record full network activity', async ({ page, shadowTrace }) => {
  shadowTrace.node('network.full_capture');
  shadowTrace.level('behavioral');
  
  // Start HAR recording
  await page.routeFromHAR('shadow-report/network.har', { 
    update: true,
    updateContent: 'embed',
  });
  
  await page.goto('/app');
  // ... test actions ...
  
  // HAR file now contains full network evidence
  shadowTrace.evidence('har_captured', { path: 'shadow-report/network.har' });
});
```
