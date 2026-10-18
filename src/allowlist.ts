import type { ISettingRegistry } from '@jupyterlab/settingregistry';

/**
 * The setting that holds the command IDs the executor may run.
 */
export const ALLOWED_COMMANDS_KEY = 'allowedCommands';

/**
 * Read the allowlist from the composite settings.
 *
 * Entries that are not strings are ignored, so a hand-edited settings file
 * cannot break the widget or the relay.
 */
export function getAllowedCommands(
  settings: ISettingRegistry.ISettings
): string[] {
  const value = settings.get(ALLOWED_COMMANDS_KEY).composite;
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === 'string');
}

/**
 * Serializes the read-modify-write of the allowlist across calls in this tab.
 */
let writeQueue: Promise<unknown> = Promise.resolve();

/**
 * Add one command ID to the allowlist through the setting registry.
 *
 * The registry is reloaded first, so an entry another tab saved since this
 * tab last read the setting is kept in the write. Calls run one at a time, so
 * two Add clicks cannot overwrite each other through a stale read.
 *
 * Returns true when the ID was added, false when it was already allowed.
 */
export function addAllowedCommand(
  settings: ISettingRegistry.ISettings,
  registry: ISettingRegistry,
  commandId: string
): Promise<boolean> {
  const result = writeQueue.then(async () => {
    await registry.reload(settings.id);
    const allowed = getAllowedCommands(settings);
    if (allowed.includes(commandId)) {
      return false;
    }
    await settings.set(ALLOWED_COMMANDS_KEY, [...allowed, commandId]);
    return true;
  });
  // A rejected reload or save reaches this call's caller without stopping
  // the calls queued after it.
  writeQueue = result.catch(() => undefined);
  return result;
}
