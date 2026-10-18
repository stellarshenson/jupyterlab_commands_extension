import type { ISettingRegistry } from '@jupyterlab/settingregistry';

import { addAllowedCommand, getAllowedCommands } from '../allowlist';

const PLUGIN_ID = 'jupyterlab_commands_extension:plugin';

interface IFakeSettings {
  settings: ISettingRegistry.ISettings;
  registry: ISettingRegistry;
  writes: unknown[];
  setRemote: (value: unknown) => void;
}

function fakeSettings(initial: unknown): IFakeSettings {
  let stored = initial;
  let composite = initial;
  const writes: unknown[] = [];
  const settings = {
    id: PLUGIN_ID,
    get: () => ({ composite, user: composite }),
    set: async (_key: string, value: unknown) => {
      await Promise.resolve();
      composite = value;
      stored = value;
      writes.push(value);
    }
  } as unknown as ISettingRegistry.ISettings;
  const registry = {
    reload: async () => {
      composite = stored;
      return settings;
    }
  } as unknown as ISettingRegistry;
  return {
    settings,
    registry,
    writes,
    setRemote: (value: unknown) => {
      stored = value;
    }
  };
}

describe('getAllowedCommands', () => {
  it('returns only the string entries of the composite value', () => {
    const fake = fakeSettings(['a', 3, 'b']);
    expect(getAllowedCommands(fake.settings)).toEqual(['a', 'b']);
  });

  it('returns an empty list when the setting is not an array', () => {
    expect(getAllowedCommands(fakeSettings(undefined).settings)).toEqual([]);
    expect(getAllowedCommands(fakeSettings('a').settings)).toEqual([]);
  });
});

describe('addAllowedCommand', () => {
  it('appends the command ID and persists it through set', async () => {
    const fake = fakeSettings(['a']);
    await expect(
      addAllowedCommand(fake.settings, fake.registry, 'b')
    ).resolves.toBe(true);
    expect(fake.writes).toEqual([['a', 'b']]);
    expect(getAllowedCommands(fake.settings)).toEqual(['a', 'b']);
  });

  it('returns false and writes nothing for an allowed command', async () => {
    const fake = fakeSettings(['a']);
    await expect(
      addAllowedCommand(fake.settings, fake.registry, 'a')
    ).resolves.toBe(false);
    expect(fake.writes).toEqual([]);
  });

  it('starts a list when the setting is missing', async () => {
    const fake = fakeSettings(undefined);
    await expect(
      addAllowedCommand(fake.settings, fake.registry, 'a')
    ).resolves.toBe(true);
    expect(fake.writes).toEqual([['a']]);
  });

  it('replaces a non-array setting with a list holding the command', async () => {
    const fake = fakeSettings('a');
    await expect(
      addAllowedCommand(fake.settings, fake.registry, 'b')
    ).resolves.toBe(true);
    expect(fake.writes).toEqual([['b']]);
  });

  it('keeps an entry another tab added, as exposed by the reload', async () => {
    const fake = fakeSettings(['a']);
    fake.setRemote(['a', 'added-elsewhere']);

    await expect(
      addAllowedCommand(fake.settings, fake.registry, 'b')
    ).resolves.toBe(true);

    expect(fake.writes).toEqual([['a', 'added-elsewhere', 'b']]);
  });

  it('serializes two concurrent adds so both persist', async () => {
    const fake = fakeSettings([]);

    await expect(
      Promise.all([
        addAllowedCommand(fake.settings, fake.registry, 'first'),
        addAllowedCommand(fake.settings, fake.registry, 'second')
      ])
    ).resolves.toEqual([true, true]);

    expect(fake.writes[fake.writes.length - 1]).toEqual(['first', 'second']);
  });

  it('propagates a reload failure and lets the next add run', async () => {
    const fake = fakeSettings(['a']);
    const failing = {
      reload: async () => {
        throw new Error('reload failed');
      }
    } as unknown as ISettingRegistry;

    await expect(
      addAllowedCommand(fake.settings, failing, 'b')
    ).rejects.toThrow('reload failed');

    await expect(
      addAllowedCommand(fake.settings, fake.registry, 'b')
    ).resolves.toBe(true);
    expect(fake.writes).toEqual([['a', 'b']]);
  });
});
