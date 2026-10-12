/**
 * Contract tests for the public / installed build.
 *
 *  - `ConfigManager.buildClientConfig` must resolve the backend interpreter
 *    with the priority: explicit overrides > user file config > verified
 *    launcher env (`SIADA_PYTHON_PATH`) > portable `python3` / `python` on
 *    PATH.  No machine-specific path (conda/miniconda) and no
 *    source-checkout path derived from the cwd may ever be fabricated.
 *  - The resulting `ClientConfig` must still satisfy the existing adapter
 *    spawn contract: module mode spawns `<python> -m siada.entrypoint.siadahub`
 *    with cwd = workingDir; without an interpreter/module root the adapter
 *    falls back to the `siada-cli` executable.
 *
 * Nothing is spawned: the spawn parameters are asserted through the adapter's
 * pure command builder.  Run with a throwaway HOME (`HOME=$(mktemp -d)`) so no
 * real user config or log file is touched.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { ConfigManager } from '../src/utils/config.js';
import { SiadaACPAdapter } from '../src/acp/adapter.js';
import type { ClientConfig } from '../src/types/index.js';

const MANAGED_ENV = ['PATH', 'Path', 'SIADA_PYTHON_PATH', 'SIADA_MODULE_PATH'] as const;

/** Create an executable stand-in for a Python interpreter (never launched). */
function createFakePython(dir: string, name: string): string {
  const file = join(dir, name);
  writeFileSync(file, '#!/bin/sh\nexit 0\n');
  chmodSync(file, 0o755); // writeFileSync's mode is masked by the umask
  return file;
}

/** The spawn parameters the adapter would use for a given ClientConfig. */
function spawnParamsFor(config: ClientConfig): { command: string; args: string[] } {
  return (new SiadaACPAdapter() as any).buildCommand(config);
}

describe('ConfigManager.buildClientConfig — backend resolution contract', () => {
  let manager: ConfigManager;
  let tempDir: string;
  let originalCwd: string;
  let originalEnv: Record<string, string | undefined>;

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'siada-ui-config-'));
    originalCwd = process.cwd();
    originalEnv = {};
    for (const key of MANAGED_ENV) originalEnv[key] = process.env[key];
    delete process.env.SIADA_PYTHON_PATH;
    delete process.env.SIADA_MODULE_PATH;

    manager = new ConfigManager();
    // Drop whatever user config was loaded from HOME; every tier is set
    // explicitly by the test that exercises it.
    manager.set('siada', {});
  });

  afterEach(() => {
    process.chdir(originalCwd);
    for (const key of MANAGED_ENV) {
      if (originalEnv[key] === undefined) delete process.env[key];
      else process.env[key] = originalEnv[key];
    }
    rmSync(tempDir, { recursive: true, force: true });
  });

  it('prefers explicit overrides over file config, launcher env and PATH', () => {
    process.env.PATH = tempDir;
    process.env.SIADA_PYTHON_PATH = join(tempDir, 'launcher-python');
    process.env.SIADA_MODULE_PATH = '/env/module';
    manager.set('siada', {
      pythonPath: '/file/python',
      modulePath: '/file/module',
      path: '/file/siada-cli',
      useModuleMode: false,
    });

    const config = manager.buildClientConfig({
      workingDir: '/custom/workspace',
      pythonPath: '/override/python', // not required to exist: explicit wins
      siadaModule: '/override/module',
      siadaPath: '/override/siada-cli',
      useModuleMode: true,
    });

    expect(config.pythonPath).toBe('/override/python');
    expect(config.siadaModule).toBe('/override/module');
    expect(config.siadaPath).toBe('/override/siada-cli');
    expect(config.useModuleMode).toBe(true);
    expect(config.workingDir).toBe('/custom/workspace');
  });

  it('uses user file config when no override is given, above launcher env', () => {
    process.env.SIADA_PYTHON_PATH = join(tempDir, 'launcher-python');
    process.env.SIADA_MODULE_PATH = '/env/module';
    manager.set('siada', { pythonPath: '/file/python', modulePath: '/file/module' });

    const config = manager.buildClientConfig();

    expect(config.pythonPath).toBe('/file/python');
    expect(config.siadaModule).toBe('/file/module');
    expect(config.workingDir).toBe(process.cwd());
  });

  it('accepts the launcher-provided interpreter/module root when verified', () => {
    const launcherPython = createFakePython(tempDir, 'launcher-python');
    process.env.SIADA_PYTHON_PATH = launcherPython;
    process.env.SIADA_MODULE_PATH = '/launcher/import-root';
    process.env.PATH = '';

    const config = manager.buildClientConfig();

    expect(config.pythonPath).toBe(launcherPython);
    expect(config.siadaModule).toBe('/launcher/import-root');
  });

  it('rejects a stale launcher interpreter and falls back to python3 on PATH', () => {
    const python3 = createFakePython(tempDir, 'python3');
    process.env.SIADA_PYTHON_PATH = join(tempDir, 'missing-python');
    process.env.PATH = tempDir;

    expect(manager.buildClientConfig().pythonPath).toBe(python3);
  });

  it('resolves a bare launcher interpreter name through PATH', () => {
    const python3 = createFakePython(tempDir, 'python3');
    process.env.SIADA_PYTHON_PATH = 'python3';
    process.env.PATH = tempDir;

    expect(manager.buildClientConfig().pythonPath).toBe(python3);
  });

  it('defaults to the portable python3 on PATH (no hard-coded/miniconda path)', () => {
    const python3 = createFakePython(tempDir, 'python3');
    createFakePython(tempDir, 'python');
    process.env.PATH = tempDir;

    const config = manager.buildClientConfig();

    expect(config.pythonPath).toBe(python3);
    expect(config.pythonPath).not.toContain('miniconda');
    expect(config.siadaModule).toBeUndefined();
  });

  it('falls back to `python` when python3 is not installed', () => {
    const python = createFakePython(tempDir, 'python');
    process.env.PATH = tempDir;

    expect(manager.buildClientConfig().pythonPath).toBe(python);
  });

  it('leaves pythonPath undefined when no interpreter exists on PATH', () => {
    process.env.PATH = tempDir;

    const config = manager.buildClientConfig();

    expect(config.pythonPath).toBeUndefined();
    // Adapter gate (useModuleMode && pythonPath && siadaModule) fails -> the
    // executable fallback is used instead of a dangling interpreter path.
    expect(spawnParamsFor(config).command).toBe('siada-cli');
  });

  it('defaults workingDir to process.cwd() and honours a custom workingDir', () => {
    process.env.PATH = tempDir;

    expect(manager.buildClientConfig().workingDir).toBe(process.cwd());
    expect(manager.buildClientConfig({ workingDir: '/custom/workspace' }).workingDir).toBe(
      '/custom/workspace'
    );
  });

  it('never derives the module root from the cwd (no source-checkout assumption)', () => {
    const python3 = createFakePython(tempDir, 'python3');
    process.env.PATH = tempDir;
    // Reproduce the old default: <cwd>/../siada-agenthub used to be invented
    // even though the user's workspace has nothing to do with a checkout.
    const workspace = join(tempDir, 'workspace');
    mkdirSync(workspace, { recursive: true });
    mkdirSync(join(tempDir, 'siada-agenthub'), { recursive: true });
    process.chdir(workspace);

    const config = manager.buildClientConfig();

    expect(config.workingDir).toBe(process.cwd());
    expect(config.siadaModule).toBeUndefined();
    expect(config.pythonPath).toBe(python3);
  });

  it('normalises the CLI string form of useModuleMode to a boolean', () => {
    // src/cli.ts computes: options.useModuleMode || (pythonPath && siadaModule) || false
    const cliValue = '/override/module' as unknown as boolean;

    const config = manager.buildClientConfig({
      pythonPath: '/override/python',
      siadaModule: '/override/module',
      useModuleMode: cliValue,
    });

    expect(config.useModuleMode).toBe(true);
  });

  it('module mode config spawns `<python> -m siada.entrypoint.siadahub` in workingDir', () => {
    const python = createFakePython(tempDir, 'launcher-python');
    const config = manager.buildClientConfig({
      workingDir: tempDir,
      pythonPath: python,
      siadaModule: '/launcher/import-root',
      useModuleMode: true,
      acpMode: true,
    });

    const { command, args } = spawnParamsFor(config);

    expect(command).toBe(python);
    expect(args.slice(0, 2)).toEqual(['-m', 'siada.entrypoint.siadahub']);
    expect(args).toContain('--acp');
    // The spawned backend keeps the user's workspace as cwd, not the checkout.
    expect(config.workingDir).toBe(tempDir);
  });

  it('executable mode spawns the configured siada-cli binary', () => {
    const config = manager.buildClientConfig({
      siadaPath: '/opt/siada/bin/siada-cli',
      useModuleMode: false,
    });

    const { command, args } = spawnParamsFor(config);

    expect(command).toBe('/opt/siada/bin/siada-cli');
    expect(args).not.toContain('-m');
    expect(args).toContain('--acp');
  });

  it('honours an explicit module/executable choice regardless of PATH defaults', () => {
    const python3 = createFakePython(tempDir, 'python3');
    process.env.PATH = tempDir;

    const moduleMode = manager.buildClientConfig({
      pythonPath: python3,
      siadaModule: tempDir,
      useModuleMode: true,
    });
    expect(spawnParamsFor(moduleMode).command).toBe(python3);

    const executableMode = manager.buildClientConfig({
      pythonPath: python3,
      siadaModule: tempDir,
      useModuleMode: false,
    });
    expect(spawnParamsFor(executableMode).command).toBe('siada-cli');
  });
});