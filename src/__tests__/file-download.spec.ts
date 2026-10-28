import type { JupyterFrontEnd } from '@jupyterlab/application';
import type { ICommandPalette } from '@jupyterlab/apputils';
import type { ISettingRegistry } from '@jupyterlab/settingregistry';
import { CommandRegistry } from '@lumino/commands';

// The tests never run the reference-tab command, so mock the UI modules it
// reaches for: the real ones pull an untranspiled ESM chain.
jest.mock('@jupyterlab/apputils', () => ({
  MainAreaWidget: jest.fn()
}));
jest.mock('@jupyterlab/ui-components', () => ({
  textEditorIcon: null
}));

import plugin from '../index';

const COMMAND_ID = 'file:download';

interface IFakeApp {
  app: JupyterFrontEnd;
  get: jest.Mock;
  getDownloadUrl: jest.Mock;
}

/**
 * Activate the plugin with a registry whose settings load fails, so the relay
 * never starts, and return the contents mocks the command executes against.
 */
async function activatePlugin(): Promise<IFakeApp> {
  const commands = new CommandRegistry();
  const get = jest.fn();
  const getDownloadUrl = jest.fn();
  const app = {
    commands,
    serviceManager: { contents: { get, getDownloadUrl } }
  } as unknown as JupyterFrontEnd;
  const palette = { addItem: jest.fn() } as unknown as ICommandPalette;
  const registry = {
    load: jest.fn().mockRejectedValue(new Error('no settings in this test'))
  } as unknown as ISettingRegistry;
  await plugin.activate(app, palette, registry);
  return { app, get, getDownloadUrl };
}

function spyOnAnchorClick(): jest.Mock {
  const clicked = jest.fn();
  jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement
  ) {
    clicked({ element: this, parent: this.parentNode });
  });
  return clicked;
}

describe('file:download', () => {
  it('registers the command with the describedBy path argument', async () => {
    const { app } = await activatePlugin();

    expect(app.commands.hasCommand(COMMAND_ID)).toBe(true);
    expect(app.commands.label(COMMAND_ID)).toBe('Download File');
    const description = await app.commands.describedBy(COMMAND_ID);
    const args = description.args as Record<string, any>;
    expect(args.type).toBe('object');
    expect(args.properties.path.type).toBe('string');
    expect(args.properties.path.description).toBe(
      'the file path relative to the server root'
    );
    expect(args.required).toEqual(['path']);
  });

  it('rejects when path is missing or not a non-empty string', async () => {
    const { app, get } = await activatePlugin();

    await expect(app.commands.execute(COMMAND_ID, {})).rejects.toThrow(
      'non-empty path'
    );
    await expect(
      app.commands.execute(COMMAND_ID, { path: '' })
    ).rejects.toThrow('non-empty path');
    await expect(app.commands.execute(COMMAND_ID, { path: 3 })).rejects.toThrow(
      'non-empty path'
    );
    expect(get).not.toHaveBeenCalled();
  });

  it('rejects a directory and clicks nothing', async () => {
    const { app, get, getDownloadUrl } = await activatePlugin();
    get.mockResolvedValue({ type: 'directory', path: 'data' });
    const clicked = spyOnAnchorClick();

    await expect(
      app.commands.execute(COMMAND_ID, { path: 'data' })
    ).rejects.toThrow(/directory: data/);
    expect(get).toHaveBeenCalledWith('data', { content: false });
    expect(getDownloadUrl).not.toHaveBeenCalled();
    expect(clicked).not.toHaveBeenCalled();
  });

  it('downloads a file through a temporary anchor', async () => {
    const { app, get, getDownloadUrl } = await activatePlugin();
    get.mockResolvedValue({ type: 'file', path: 'data/report.csv' });
    const url = 'http://host/files/data/report.csv';
    getDownloadUrl.mockResolvedValue(url);
    const clicked = spyOnAnchorClick();

    await expect(
      app.commands.execute(COMMAND_ID, { path: 'data/report.csv' })
    ).resolves.toBeUndefined();
    expect(get).toHaveBeenCalledWith('data/report.csv', { content: false });
    expect(getDownloadUrl).toHaveBeenCalledWith('data/report.csv');
    expect(clicked).toHaveBeenCalledTimes(1);
    const { element: anchor, parent } = clicked.mock.calls[0][0] as {
      element: HTMLAnchorElement;
      parent: Node | null;
    };
    expect(anchor.href).toBe(url);
    expect(anchor.download).toBe('');
    expect(parent).toBe(document.body);
    expect(document.querySelector('a')).toBeNull();
  });
});
