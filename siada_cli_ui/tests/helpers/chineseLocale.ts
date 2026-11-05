import { beforeEach, afterEach } from 'vitest';
import { setUiLanguage } from '../../src/i18n/index.js';

// Keep existing Chinese presentation regressions explicit about their locale.
beforeEach(() => setUiLanguage('zh-CN'));
afterEach(() => setUiLanguage('en'));