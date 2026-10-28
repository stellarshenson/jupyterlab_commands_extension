import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { ICommandPalette, MainAreaWidget } from '@jupyterlab/apputils';

import { ISettingRegistry } from '@jupyterlab/settingregistry';

import { textEditorIcon } from '@jupyterlab/ui-components';

import { RelayClient } from './relay';
import { CommandsReferenceWidget } from './widget';

/**
 * Command IDs for the extension
 */
namespace CommandIDs {
  export const open = 'jupyterlab-commands-reference:open';
  export const download = 'file:download';
}

/**
 * The id of this plugin. It is also the id of its settings schema.
 */
const PLUGIN_ID = 'jupyterlab_commands_extension:plugin';

/**
 * Track the widget instance to prevent duplicates
 */
let widget: MainAreaWidget<CommandsReferenceWidget> | null = null;

/**
 * Track the relay client so plugin teardown can stop it
 */
let relay: RelayClient | null = null;

/**
 * Initialization data for the jupyterlab_commands_extension extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: PLUGIN_ID,
  description:
    'Display all available JupyterLab commands with their full reference IDs and arguments in a dedicated tab',
  autoStart: true,
  requires: [ICommandPalette, ISettingRegistry],
  activate: async (
    app: JupyterFrontEnd,
    palette: ICommandPalette,
    settingRegistry: ISettingRegistry
  ) => {
    console.log(
      'JupyterLab extension jupyterlab_commands_extension is activated!'
    );

    let settings: ISettingRegistry.ISettings | null = null;
    try {
      settings = await settingRegistry.load(PLUGIN_ID);
    } catch (reason) {
      console.error(
        'Commands Reference: cannot load the allowedCommands setting',
        reason
      );
    }

    // Register the command
    app.commands.addCommand(CommandIDs.open, {
      label: 'Show Commands Reference',
      caption:
        'Display all available JupyterLab commands with their IDs and arguments',
      execute: () => {
        // Create widget if it doesn't exist or was disposed
        if (!widget || widget.isDisposed) {
          const content = new CommandsReferenceWidget(
            app.commands,
            settings,
            settingRegistry
          );
          widget = new MainAreaWidget({ content });
          widget.id = 'jp-commands-reference';
          widget.title.label = 'Commands Reference';
          widget.title.icon = textEditorIcon;
          widget.title.closable = true;

          // Clear reference when widget is disposed
          widget.disposed.connect(() => {
            widget = null;
          });
        }

        // Add to main area if not already attached
        if (!widget.isAttached) {
          app.shell.add(widget, 'main');
        }

        // Activate the widget
        app.shell.activateById(widget.id);
      }
    });

    // Add command to palette under Help category
    palette.addItem({
      command: CommandIDs.open,
      category: 'Help'
    });

    // Download a file the contents API serves to the computer that runs
    // the browser tab.
    app.commands.addCommand(CommandIDs.download, {
      label: 'Download File',
      caption: 'Download a file from the server to the local computer',
      describedBy: () => ({
        args: {
          type: 'object',
          properties: {
            path: {
              type: 'string',
              description: 'the file path relative to the server root'
            }
          },
          required: ['path']
        }
      }),
      execute: async args => {
        const path = typeof args.path === 'string' ? args.path : '';
        if (!path) {
          throw new Error('file:download requires a non-empty path argument');
        }
        const model = await app.serviceManager.contents.get(path, {
          content: false
        });
        if (model.type === 'directory') {
          throw new Error(`file:download refuses a directory: ${path}`);
        }
        const url = await app.serviceManager.contents.getDownloadUrl(
          model.path
        );
        const element = document.createElement('a');
        element.href = url;
        element.download = '';
        document.body.appendChild(element);
        element.click();
        document.body.removeChild(element);
      }
    });

    if (settings) {
      relay = new RelayClient({
        app,
        commands: app.commands,
        settings,
        registry: settingRegistry
      });
      relay.start();
    }
  },
  deactivate: () => {
    if (relay) {
      relay.dispose();
      relay = null;
    }
  }
};

export default plugin;
