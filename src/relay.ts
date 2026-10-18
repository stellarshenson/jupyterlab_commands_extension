import type { JupyterFrontEnd } from '@jupyterlab/application';
import { PageConfig, URLExt } from '@jupyterlab/coreutils';
import { ServerConnection } from '@jupyterlab/services';
import type { ISettingRegistry } from '@jupyterlab/settingregistry';
import type { CommandRegistry } from '@lumino/commands';

import { getAllowedCommands } from './allowlist';
import { collectCommandDescriptors } from './commands';

/**
 * The server namespace that holds the relay endpoints.
 */
export const API_NAMESPACE = 'jupyterlab-commands';

/**
 * How long to wait before retrying after a failed request.
 */
const RETRY_DELAY_MS = 1000;

/**
 * How long to coalesce command registry changes into one registration.
 */
const REGISTER_DEBOUNCE_MS = 250;

/**
 * One command the Python relay asks this tab to run.
 */
interface IRelayRequest {
  id: string;
  command: string;
  args: Record<string, unknown> | null;
  allowed: string[];
}

/**
 * A client of the Python command relay.
 *
 * It registers the command registry and the allowlist, long-polls for
 * requests, runs each allowed command and posts the result. Every failure is
 * reported to the console, never thrown into the UI.
 */
export class RelayClient {
  private _app: JupyterFrontEnd;
  private _commands: CommandRegistry;
  private _settings: ISettingRegistry.ISettings;
  private _registry: ISettingRegistry;
  private _clientId: string;
  private _serverSettings: ServerConnection.ISettings;
  private _abortController = new AbortController();
  private _disposed = false;
  private _started = false;
  private _registering = false;
  private _registerAgain = false;
  private _registerTimer: number | null = null;

  constructor(options: RelayClient.IOptions) {
    this._app = options.app;
    this._commands = options.commands;
    this._settings = options.settings;
    this._registry = options.registry;
    this._clientId =
      'jupyterlab-commands-' +
      Date.now().toString(36) +
      '-' +
      Math.random().toString(36).slice(2);
    this._serverSettings = ServerConnection.makeSettings();
  }

  /**
   * Whether the client has been disposed.
   */
  get isDisposed(): boolean {
    return this._disposed;
  }

  /**
   * Register, start the long poll and listen for changes.
   */
  start(): void {
    if (this._started || this._disposed) {
      return;
    }
    this._started = true;
    this._settings.changed.connect(this._onSettingsChanged, this);
    this._commands.commandChanged.connect(this._onCommandsChanged, this);
    void this._register();
    void this._pollLoop();
  }

  /**
   * Stop the long poll and drop the listeners.
   */
  dispose(): void {
    if (this._disposed) {
      return;
    }
    this._disposed = true;
    this._abortController.abort();
    this._settings.changed.disconnect(this._onSettingsChanged, this);
    this._commands.commandChanged.disconnect(this._onCommandsChanged, this);
    if (this._registerTimer !== null) {
      clearTimeout(this._registerTimer);
      this._registerTimer = null;
    }
  }

  private _onSettingsChanged(): void {
    void this._register();
  }

  private _onCommandsChanged(): void {
    if (this._disposed || this._registerTimer !== null) {
      return;
    }
    this._registerTimer = window.setTimeout(() => {
      this._registerTimer = null;
      void this._register();
    }, REGISTER_DEBOUNCE_MS);
  }

  /**
   * Send the current commands and allowlist to the server.
   *
   * Concurrent calls coalesce: a call made while registration is in flight
   * runs again after it finishes.
   */
  private async _register(): Promise<void> {
    if (this._disposed) {
      return;
    }
    if (this._registering) {
      this._registerAgain = true;
      return;
    }
    this._registering = true;
    try {
      const commands = await collectCommandDescriptors(this._commands);
      if (this._disposed) {
        return;
      }
      await this._post('register', {
        client_id: this._clientId,
        commands: commands.map(info => ({
          id: info.id,
          label: info.label,
          caption: info.caption,
          args: info.args
        })),
        allowed: getAllowedCommands(this._settings)
      });
    } catch (error) {
      this._report(error);
    } finally {
      this._registering = false;
      if (this._registerAgain && !this._disposed) {
        this._registerAgain = false;
        void this._register();
      }
    }
  }

  /**
   * Long-poll for requests until disposal.
   */
  private async _pollLoop(): Promise<void> {
    while (!this._disposed) {
      let request: IRelayRequest | null = null;
      try {
        const answer = await this._get('pending');
        if (answer && answer.request) {
          request = answer.request as IRelayRequest;
        }
      } catch (error) {
        if (this._disposed) {
          return;
        }
        const status = (error as { status?: number } | null)?.status;
        if (status === 404) {
          // The server forgot this client, for example after a restart.
          void this._register();
        }
        this._report(error);
        await this._delay(RETRY_DELAY_MS);
        continue;
      }

      if (request && !this._disposed) {
        await this._handleRequest(request);
      }
    }
  }

  /**
   * Run one request and post its result.
   */
  private async _handleRequest(request: IRelayRequest): Promise<void> {
    let allowed: Set<string>;
    try {
      // Another tab may have saved the setting since this tab last read it,
      // so reload before deciding whether the command is allowed.
      await this._registry.reload(this._settings.id);
      allowed = new Set(getAllowedCommands(this._settings));
    } catch (reason) {
      // Fail closed: without a fresh allowlist, run nothing.
      this._report(reason);
      try {
        await this._post('result', {
          request_id: request.id,
          ok: false,
          data: null,
          error: 'the allowlist could not be reloaded'
        });
      } catch (error) {
        this._report(error);
      }
      return;
    }
    let ok = false;
    let data: unknown = null;
    let error: string | null = null;

    if (typeof request.command !== 'string' || !allowed.has(request.command)) {
      error = `command ${String(request.command)} is not in the allowlist`;
    } else {
      try {
        data = await this._app.commands.execute(
          request.command,
          (request.args || {}) as any
        );
        ok = true;
      } catch (reason) {
        error = reason instanceof Error ? reason.message : String(reason);
      }
    }

    // A command can return a value that JSON cannot represent, such as a
    // Lumino widget. The command has run, so report the success without data
    // rather than failing to post the result.
    if (ok) {
      try {
        JSON.stringify(data);
      } catch {
        data = null;
      }
    }

    try {
      await this._post('result', {
        request_id: request.id,
        ok,
        data,
        error
      });
    } catch (reason) {
      this._report(reason);
    }
  }

  /**
   * Build the URL of one relay endpoint.
   */
  private _url(endpoint: string): string {
    return URLExt.join(PageConfig.getBaseUrl(), API_NAMESPACE, 'api', endpoint);
  }

  private _get(endpoint: string): Promise<any> {
    const url =
      this._url(endpoint) + '?client_id=' + encodeURIComponent(this._clientId);
    return this._request(url, { method: 'GET' });
  }

  private _post(endpoint: string, body: unknown): Promise<any> {
    return this._request(this._url(endpoint), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
  }

  private async _request(url: string, init: RequestInit): Promise<any> {
    const response = await ServerConnection.makeRequest(
      url,
      {
        cache: 'no-store',
        credentials: 'same-origin',
        ...init,
        signal: this._abortController.signal
      },
      this._serverSettings
    );

    const text = await response.text();
    let data: any = null;
    if (text.length > 0) {
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }

    if (!response.ok) {
      let message = response.statusText;
      if (data && typeof data === 'object') {
        if (typeof data.error === 'string') {
          message = data.error;
        } else if (data.error && typeof data.error.message === 'string') {
          message = data.error.message;
        }
      }
      const error = new Error(`HTTP ${response.status}: ${message}`);
      (error as Error & { status?: number }).status = response.status;
      throw error;
    }

    return data;
  }

  private _report(error: unknown): void {
    console.warn('Commands relay:', error);
  }

  private _delay(milliseconds: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
  }
}

/**
 * The namespace for the relay client types.
 */
export namespace RelayClient {
  export interface IOptions {
    app: JupyterFrontEnd;
    commands: CommandRegistry;
    settings: ISettingRegistry.ISettings;
    registry: ISettingRegistry;
  }
}
