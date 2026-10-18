import { Widget } from '@lumino/widgets';
import { CommandRegistry } from '@lumino/commands';
import type { ISettingRegistry } from '@jupyterlab/settingregistry';

import { addAllowedCommand, getAllowedCommands } from './allowlist';
import { collectCommands, describeCommand, ICommandInfo } from './commands';

/**
 * A widget that displays all registered JupyterLab commands
 */
export class CommandsReferenceWidget extends Widget {
  private _commands: CommandRegistry;
  private _settings: ISettingRegistry.ISettings | null;
  private _registry: ISettingRegistry | null;
  private _searchInput!: HTMLInputElement;
  private _countSpan!: HTMLSpanElement;
  private _tbody!: HTMLTableSectionElement;
  private _commandsCache: ICommandInfo[] = [];
  private _argsCache: Map<string, string> = new Map();

  constructor(
    commands: CommandRegistry,
    settings: ISettingRegistry.ISettings | null = null,
    registry: ISettingRegistry | null = null
  ) {
    super();
    this._commands = commands;
    this._settings = settings;
    this._registry = registry;
    this.addClass('jp-CommandsReferenceWidget');

    if (this._settings) {
      this._settings.changed.connect(this._onSettingsChanged, this);
    }

    // Build DOM structure
    this._buildHeader();
    this._buildContent();

    // Initial load
    void this._loadCommands();
  }

  /**
   * Dispose the widget and drop the settings listener.
   */
  dispose(): void {
    if (this._settings) {
      this._settings.changed.disconnect(this._onSettingsChanged, this);
    }
    super.dispose();
  }

  /**
   * Reflect a settings change in the executor buttons.
   */
  private _onSettingsChanged(): void {
    this._updateExecutorButtons();
  }

  /**
   * Build the header with search input and count
   */
  private _buildHeader(): void {
    const header = document.createElement('div');
    header.className = 'jp-CommandsReferenceWidget-header';

    // Search input
    this._searchInput = document.createElement('input');
    this._searchInput.type = 'text';
    this._searchInput.placeholder = 'Filter commands...';
    this._searchInput.className = 'jp-CommandsReferenceWidget-search';
    this._searchInput.addEventListener('input', () => {
      this._filterCommands();
    });
    header.appendChild(this._searchInput);

    // Command count
    this._countSpan = document.createElement('span');
    this._countSpan.className = 'jp-CommandsReferenceWidget-count';
    header.appendChild(this._countSpan);

    this.node.appendChild(header);
  }

  /**
   * Build the content area with commands table
   */
  private _buildContent(): void {
    const content = document.createElement('div');
    content.className = 'jp-CommandsReferenceWidget-content';

    const table = document.createElement('table');
    table.className = 'jp-CommandsReferenceWidget-table';

    // Table header
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    const headers = [
      'Command ID',
      'Label',
      'Description',
      'Arguments',
      'Command Executor'
    ];
    for (const headerText of headers) {
      const th = document.createElement('th');
      th.textContent = headerText;
      headerRow.appendChild(th);
    }
    thead.appendChild(headerRow);
    table.appendChild(thead);

    // Table body
    this._tbody = document.createElement('tbody');
    table.appendChild(this._tbody);

    content.appendChild(table);
    this.node.appendChild(content);
  }

  /**
   * Load all commands from the registry
   */
  private async _loadCommands(): Promise<void> {
    try {
      const commandIds = this._commands.listCommands();
      console.log(`Commands Reference: Found ${commandIds.length} commands`);
      this._commandsCache = collectCommands(this._commands);

      // Render initial table
      this._renderTable(this._commandsCache);

      // Load arguments asynchronously
      void this._loadArguments();
    } catch (error) {
      console.error('Commands Reference: Error loading commands', error);
    }
  }

  /**
   * Load command arguments asynchronously
   */
  private async _loadArguments(): Promise<void> {
    const batchSize = 50;
    const commands = this._commandsCache;

    for (let i = 0; i < commands.length; i += batchSize) {
      const batch = commands.slice(i, i + batchSize);

      await Promise.all(
        batch.map(async cmd => {
          const argsStr = await describeCommand(this._commands, cmd.id);
          if (argsStr) {
            cmd.args = argsStr;
            this._argsCache.set(cmd.id, argsStr);

            // Update the cell if visible
            this._updateArgsCell(cmd.id, argsStr);
          }
        })
      );

      // Yield to allow UI updates
      await new Promise(resolve => setTimeout(resolve, 0));
    }
  }

  /**
   * Update a specific args cell in the table
   */
  private _updateArgsCell(commandId: string, argsStr: string): void {
    const rows = Array.from(this._tbody.querySelectorAll('tr'));
    for (const row of rows) {
      const idCell = row.querySelector('td:first-child');
      if (idCell && idCell.textContent === commandId) {
        const argsCell = row.querySelector(
          'td:nth-child(4)'
        ) as HTMLElement | null;
        if (argsCell) {
          argsCell.textContent = argsStr;
          argsCell.title = argsStr;
        }
        break;
      }
    }
  }

  /**
   * Render the commands table
   */
  private _renderTable(commands: ICommandInfo[]): void {
    while (this._tbody.firstChild) {
      this._tbody.removeChild(this._tbody.firstChild);
    }

    for (const cmd of commands) {
      const row = document.createElement('tr');

      // Command ID cell
      const idCell = document.createElement('td');
      idCell.className = 'jp-CommandsReferenceWidget-commandId';
      idCell.textContent = cmd.id;
      idCell.title = cmd.id;
      row.appendChild(idCell);

      // Label cell
      const labelCell = document.createElement('td');
      labelCell.textContent = cmd.label;
      labelCell.title = cmd.label;
      row.appendChild(labelCell);

      // Description cell
      const descCell = document.createElement('td');
      descCell.textContent = cmd.caption;
      descCell.title = cmd.caption;
      row.appendChild(descCell);

      // Arguments cell
      const argsCell = document.createElement('td');
      const cachedArgs = this._argsCache.get(cmd.id);
      argsCell.textContent = cachedArgs || cmd.args || '';
      argsCell.title = cachedArgs || cmd.args || '';
      row.appendChild(argsCell);

      // Executor cell
      const executorCell = document.createElement('td');
      executorCell.className = 'jp-CommandsReferenceWidget-executor';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'jp-CommandsReferenceWidget-add';
      button.dataset.commandId = cmd.id;
      button.addEventListener('click', () => {
        void this._addToExecutor(cmd.id, button);
      });
      if (this._isAllowed(cmd.id)) {
        button.textContent = 'Added';
        button.disabled = true;
      } else {
        button.textContent = 'Add to command executor';
        button.disabled = !this._settings || !this._registry;
      }
      executorCell.appendChild(button);
      row.appendChild(executorCell);

      this._tbody.appendChild(row);
    }

    this._updateCount(commands.length, this._commandsCache.length);
  }

  /**
   * Filter commands based on search input
   */
  private _filterCommands(): void {
    const query = this._searchInput.value.toLowerCase().trim();

    if (!query) {
      this._renderTable(this._commandsCache);
      return;
    }

    const filtered = this._commandsCache.filter(cmd => {
      return (
        cmd.id.toLowerCase().includes(query) ||
        cmd.label.toLowerCase().includes(query) ||
        cmd.caption.toLowerCase().includes(query)
      );
    });

    this._renderTable(filtered);
  }

  /**
   * Whether a command ID is in the allowlist.
   */
  private _isAllowed(commandId: string): boolean {
    return (
      this._settings !== null &&
      getAllowedCommands(this._settings).includes(commandId)
    );
  }

  /**
   * Add one command ID to the allowlist and show the Added state.
   */
  private async _addToExecutor(
    commandId: string,
    button: HTMLButtonElement
  ): Promise<void> {
    if (!this._settings || !this._registry) {
      return;
    }
    button.disabled = true;
    try {
      await addAllowedCommand(this._settings, this._registry, commandId);
      button.textContent = 'Added';
    } catch (error) {
      console.error('Commands Reference: cannot update allowedCommands', error);
      button.textContent = 'Add to command executor';
      button.disabled = false;
    }
  }

  /**
   * Set every executor button from the current allowlist.
   */
  private _updateExecutorButtons(): void {
    const buttons = this._tbody.querySelectorAll<HTMLButtonElement>(
      'button.jp-CommandsReferenceWidget-add'
    );
    for (const button of Array.from(buttons)) {
      const commandId = button.dataset.commandId || '';
      const allowed = this._isAllowed(commandId);
      button.textContent = allowed ? 'Added' : 'Add to command executor';
      button.disabled =
        allowed || this._settings === null || this._registry === null;
    }
  }

  /**
   * Update the command count display
   */
  private _updateCount(shown: number, total: number): void {
    if (shown === total) {
      this._countSpan.textContent = `${total} commands`;
    } else {
      this._countSpan.textContent = `${shown} / ${total} commands`;
    }
  }

  /**
   * Refresh the commands list
   */
  refresh(): void {
    this._argsCache.clear();
    void this._loadCommands();
  }
}
