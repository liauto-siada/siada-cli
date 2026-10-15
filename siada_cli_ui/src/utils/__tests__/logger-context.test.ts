import { describe, it, expect, afterEach } from 'vitest';
import { mkdtempSync, readFileSync, rmSync, writeFileSync, readdirSync, utimesSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Logger, LogLevel } from '../logger.js';
import { spawn } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';

const dirs: string[] = [];
function setup(maxFileSize = 100000) {
  const logDir = mkdtempSync(join(tmpdir(), 'siada-logger-test-'));
  dirs.push(logDir);
  return { logDir, logger: new Logger({ logDir, maxFileSize, level: LogLevel.INFO, enableConsole: false }) };
}
afterEach(() => dirs.splice(0).forEach(dir => rmSync(dir, { recursive: true, force: true })));

describe('log attribution and retention', () => {
  it('keeps records when separate UI processes share and rotate the active file', async () => {
    const { logDir } = setup();
    const childModule = join(logDir, 'logger-fixture.mjs');
    writeFileSync(childModule, ts.transpileModule(
      readFileSync(new URL('../logger.ts', import.meta.url), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 } },
    ).outputText);
    const program = `
      import { Logger, LogLevel } from ${JSON.stringify(pathToFileURL(childModule).href)};
      const logger = new Logger({ maxFileSize: 4096, level: LogLevel.INFO });
      for (let i = 0; i < 60; i++) logger.info('marker-' + process.env.TEST_WORKER + '-' + i);
    `;
    await Promise.all([0, 1, 2, 3].map(worker => new Promise<void>((resolve, reject) => {
      const child = spawn(process.execPath, ['--input-type=module', '-e', program], {
        env: { ...process.env, SIADA_UI_LOG_DIR: logDir, TEST_WORKER: String(worker) },
        stdio: ['ignore', 'ignore', 'pipe'],
      });
      let error = '';
      child.stderr.on('data', chunk => { error += chunk; });
      child.on('error', reject);
      child.on('close', code => code === 0 ? resolve() : reject(new Error(error || `exit ${code}`)));
    })));
    const all = readdirSync(logDir).filter(name => name.startsWith('siada-ui') && name.endsWith('.log'))
      .map(name => readFileSync(join(logDir, name), 'utf8')).join('\n');
    const markers = all.match(/marker-\d-\d+/g) || [];
    expect(markers.length).toBe(240);
    expect(new Set(markers).size).toBe(240);
  });

  it('keeps asynchronous requests isolated and tags plain messages', async () => {
    const { logger } = setup();
    logger.setSessionId('session-main');
    await Promise.all(['a', 'b'].map(requestId =>
      logger.withContext({ sessionId: `session-${requestId}`, requestId, agent: `agent-${requestId}` }, async () => {
        await Promise.resolve();
        logger.info(`request-${requestId}`);
      })));
    logger.info('idle');
    const lines = readFileSync(logger.getLogFile()!, 'utf8').trim().split('\n');
    expect(lines[0]).toContain('"requestId":"a","agent":"agent-a"');
    expect(lines[1]).toContain('"sessionId":"session-b"');
    expect(lines[2]).toContain('"sessionId":"session-main","requestId":"-"');
    expect(lines[0]).toContain(`"pid":${process.pid}`);
  });

  it('rotates continuously and retains the active log during age cleanup', () => {
    const { logger, logDir } = setup(200);
    const oldDate = new Date(Date.now() - 8 * 86400000);
    const backup = join(logDir, 'siada-ui.2000-01-01.log');
    writeFileSync(backup, 'old backup');
    utimesSync(backup, oldDate, oldDate);
    writeFileSync(logger.getLogFile()!, 'active');
    utimesSync(logger.getLogFile()!, oldDate, oldDate);
    // A new instance must preserve the active file and remove stale backups.
    new Logger({ logDir, maxFileSize: 100000 });
    expect(readFileSync(logger.getLogFile()!, 'utf8')).toBe('active');
    expect(readdirSync(logDir)).not.toContain('siada-ui.2000-01-01.log');
    for (let i = 0; i < 4; i++) logger.info(`record-${i}`);
    const text = readdirSync(logDir).map(name => readFileSync(join(logDir, name), 'utf8')).join('');
    for (let i = 0; i < 4; i++) expect(text).toContain(`record-${i}`);
    expect(readdirSync(logDir).length).toBeGreaterThan(1);
  });
});