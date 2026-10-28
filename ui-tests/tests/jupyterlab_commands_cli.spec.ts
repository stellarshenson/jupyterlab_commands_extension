import { expect, test } from '@jupyterlab/galata';

import { ChildProcess, spawn } from 'child_process';
import { chmodSync, mkdirSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import * as path from 'path';

/**
 * The Galata port. The Playwright config and the server config read the same
 * variable, so the fake server record names the server under test.
 */
const PORT = process.env.JUPYTER_TEST_PORT || '8888';
const BASE_URL = `http://127.0.0.1:${PORT}`;

/** A secret planted in the fake server record; it must never be printed. */
const TOKEN = 'cli-sentinel-token-6f2c9a';

/** The allowlist declared by schema/plugin.json. */
const DEFAULT_ALLOWED = [
  'docmanager:open',
  'help:open',
  'apputils:notify',
  'notebook:create-new',
  'console:create',
  'terminal:create-new',
  'launcher:create',
  'jupyterlab-commands-reference:open',
  'file:download'
];

/** Every variable that could let discovery reach the developer's own lab. */
const DISCOVERY_ENV = [
  'JUPYTERLAB_COMMANDS_TOKEN',
  'JUPYTERHUB_API_TOKEN',
  'JPY_API_TOKEN',
  'JUPYTER_TOKEN',
  'JUPYTER_PORT',
  'JUPYTERHUB_SERVICE_PREFIX',
  'JUPYTERHUB_SERVICE_URL'
];

interface ICliResult {
  code: number | null;
  stdout: string;
  stderr: string;
}

/**
 * Write a fake ``jupyter`` executable that lists exactly one server: the
 * Galata server, under a record token that must stay out of the output.
 */
function fakeJupyterDirectory(): string {
  const directory = path.join(tmpdir(), 'jupyterlab-commands-cli-bin');
  mkdirSync(directory, { recursive: true });
  const script = path.join(directory, 'jupyter');
  const record = {
    port: Number(PORT),
    base_url: '/',
    token: TOKEN,
    hostname: '127.0.0.1'
  };
  writeFileSync(
    script,
    `#!/bin/sh\ncat <<'JSON'\n${JSON.stringify(record)}\nJSON\n`,
    'utf-8'
  );
  chmodSync(script, 0o755);
  return directory;
}

/**
 * Return an environment whose discovery sees only the fake server record.
 */
function isolatedEnvironment(): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    PATH: `${fakeJupyterDirectory()}${path.delimiter}${process.env.PATH ?? ''}`
  };
  for (const name of DISCOVERY_ENV) {
    delete env[name];
  }
  return env;
}

/**
 * Spawn the installed console script and collect its exit code and streams.
 *
 * The error listener reports a missing executable as a result, so a broken
 * entry point fails the assertion instead of crashing the worker.
 */
function runCli(args: string[], env: NodeJS.ProcessEnv): Promise<ICliResult> {
  return new Promise(resolve => {
    let stdout = '';
    let stderr = '';
    let settled = false;
    const finish = (result: ICliResult) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(watchdog);
      resolve(result);
    };
    const child: ChildProcess = spawn('jupyterlab-commands', args, { env });
    const watchdog = setTimeout(() => {
      child.kill();
      finish({ code: null, stdout, stderr: `${stderr}\nwatchdog: no exit` });
    }, 50000);
    child.stdout?.on('data', chunk => {
      stdout += chunk.toString();
    });
    child.stderr?.on('data', chunk => {
      stderr += chunk.toString();
    });
    child.on('error', error =>
      finish({ code: null, stdout, stderr: `${stderr}spawn failed: ${error}` })
    );
    child.on('close', code => finish({ code, stdout, stderr }));
  });
}

function expectNoToken(result: ICliResult): void {
  expect(result.stdout).not.toContain(TOKEN);
  expect(result.stderr).not.toContain(TOKEN);
}

/**
 * Wait until a registration from this page reaches the server.
 *
 * The relay selects the most recently registered tab, so the CLI then talks
 * to the page under test rather than to an earlier test's page.
 */
async function waitForRegistration(page: any): Promise<void> {
  const registered = page.waitForResponse(
    (response: any) =>
      response.url().includes('/jupyterlab-commands/api/register') &&
      response.ok(),
    { timeout: 30000 }
  );
  await page.evaluate(async () => {
    const registry = await (window as any).galata.getPlugin(
      '@jupyterlab/apputils-extension:settings'
    );
    const settings = await registry.load(
      'jupyterlab_commands_extension:plugin'
    );
    await settings.set('allowedCommands', ['apputils:notify']);
  });
  await registered;
}

test('--list names the default allowed commands and their arguments', async ({
  page
}) => {
  // Fails if the CLI stops reading the relay allowlist, or if command
  // descriptors stop carrying the arguments described by the registry.
  const env = isolatedEnvironment();
  const registered = page.waitForResponse(
    (response: any) =>
      response.url().includes('/jupyterlab-commands/api/register') &&
      response.ok(),
    { timeout: 30000 }
  );
  await page.evaluate(async (allowed: string[]) => {
    const registry = await (window as any).galata.getPlugin(
      '@jupyterlab/apputils-extension:settings'
    );
    const settings = await registry.load(
      'jupyterlab_commands_extension:plugin'
    );
    await settings.set('allowedCommands', allowed);
  }, DEFAULT_ALLOWED);
  await registered;

  const plain = await runCli(['--list'], env);
  expect(plain.code).toBe(0);
  expectNoToken(plain);
  expect(plain.stdout.trim().split('\n').sort()).toEqual(
    [...DEFAULT_ALLOWED].sort()
  );

  const json = await runCli(['--list', '--json'], env);
  expect(json.code).toBe(0);
  expectNoToken(json);
  const listing = JSON.parse(json.stdout);
  expect(listing.allowed).toEqual([...DEFAULT_ALLOWED].sort());
  const byId = new Map(
    listing.commands.map((command: any) => [command.id, command])
  );
  expect((byId.get('docmanager:open') as any).args).toContain('path: string');
  expect((byId.get('apputils:notify') as any).args).toContain(
    'message: string'
  );
});

test('execute runs an allowed command and refuses one outside the allowlist', async ({
  page
}) => {
  // Fails if the relay stops running the command in the browser, if the
  // allowlist check disappears, or if the CLI resolves anything but the
  // record's base URL.
  const env = isolatedEnvironment();
  await waitForRegistration(page);

  const message = 'cli relay e2e 4f7e';
  const allowed = runCli(
    [
      'execute',
      'apputils:notify',
      '--args',
      JSON.stringify({ message, options: { autoClose: false } })
    ],
    env
  );

  // The execute call does not answer until the browser has run the command.
  await expect(page.getByText(message)).toBeVisible({ timeout: 30000 });
  const allowedResult = await allowed;
  expect(allowedResult.code).toBe(0);
  expectNoToken(allowedResult);

  const refused = await runCli(['execute', 'settingeditor:open'], env);
  expect(refused.code).toBe(4);
  expectNoToken(refused);
  expect(refused.stderr).toContain('not in the browser allowlist');
  // The refusal names the address the CLI resolved, not just an error code.
  expect(refused.stderr).toContain(`from ${BASE_URL}`);
});

test('file:download downloads a file and reports a missing path', async ({
  page
}) => {
  // Fails if file:download stops starting the browser download of a file the
  // contents API serves, or if a missing path exits with anything but the
  // command-failure code and an error.
  const env = isolatedEnvironment();
  const registered = page.waitForResponse(
    (response: any) =>
      response.url().includes('/jupyterlab-commands/api/register') &&
      response.ok(),
    { timeout: 30000 }
  );
  await page.evaluate(
    async (allowed: string[]) => {
      const registry = await (window as any).galata.getPlugin(
        '@jupyterlab/apputils-extension:settings'
      );
      const settings = await registry.load(
        'jupyterlab_commands_extension:plugin'
      );
      await settings.set('allowedCommands', allowed);
    },
    ['file:download']
  );
  await registered;

  const name = 'cli-download-4f7e.csv';
  await page.evaluate(async file => {
    const app = (window as any).jupyterapp;
    await app.serviceManager.contents.save(
      file,
      { type: 'file', format: 'text' },
      'cli download e2e payload'
    );
  }, name);

  const downloadPromise = page.waitForEvent('download');
  const downloaded = await runCli(
    ['execute', 'file:download', '--args', JSON.stringify({ path: name })],
    env
  );
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(name);
  expect(downloaded.code).toBe(0);
  expectNoToken(downloaded);

  const missing = await runCli(
    [
      'execute',
      'file:download',
      '--args',
      JSON.stringify({ path: 'no-such-file-4f7e.csv' })
    ],
    env
  );
  expect(missing.code).toBe(5);
  expectNoToken(missing);
  expect(missing.stderr).toContain('HTTP 500');
});

test('--help names the token variables and every exit code', () => {
  // Fails if the epilog loses a token name or an exit code, or if help starts
  // requiring a running server.
  const env = { ...isolatedEnvironment(), PYTHON_COLORS: '0' };
  return runCli(['--help'], env).then(result => {
    expect(result.code).toBe(0);
    expectNoToken(result);
    for (const name of [
      'JUPYTERHUB_API_TOKEN',
      'JPY_API_TOKEN',
      'JUPYTER_TOKEN'
    ]) {
      expect(result.stdout).toContain(name);
    }
    for (const line of [
      '  0  success',
      '  2  discovery or usage error',
      '  3  no browser client',
      '  4  command not allowed',
      '  5  execution error'
    ]) {
      expect(result.stdout).toContain(line);
    }
  });
});
