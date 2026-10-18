import { CommandRegistry } from '@lumino/commands';

/**
 * Interface for cached command information
 */
export interface ICommandInfo {
  id: string;
  label: string;
  caption: string;
  args: string | null;
}

/**
 * Format arguments object as readable string
 * Handles JSON Schema format: { type: "object", properties: { argName: { type: "string" } } }
 */
export function formatArgs(args: unknown): string {
  if (!args || typeof args !== 'object') {
    return '';
  }

  const schema = args as Record<string, unknown>;

  // JSON Schema format: extract from 'properties' object
  if (schema.properties && typeof schema.properties === 'object') {
    const properties = schema.properties as Record<string, unknown>;
    const propKeys = Object.keys(properties);

    if (propKeys.length === 0) {
      return '';
    }

    const formatted = propKeys.map(key => {
      const prop = properties[key];
      if (prop && typeof prop === 'object') {
        const propObj = prop as Record<string, unknown>;
        const typeInfo = propObj.type;
        if (typeInfo) {
          return `${key}: ${typeInfo}`;
        }
      }
      return key;
    });

    return formatted.join(', ');
  }

  // Fallback: direct key-value format (non-schema)
  const keys = Object.keys(schema).filter(k => k !== 'type' && k !== '$schema');
  if (keys.length === 0) {
    return '';
  }

  return keys.join(', ');
}

/**
 * Collect the registered commands with their labels and captions.
 *
 * Some commands have label or caption functions that may fail without args,
 * so each read is guarded.
 */
export function collectCommands(commands: CommandRegistry): ICommandInfo[] {
  const infos: ICommandInfo[] = [];

  for (const id of commands.listCommands()) {
    let label = '';
    let caption = '';

    try {
      label = commands.label(id) || '';
    } catch {
      label = '';
    }

    try {
      caption = commands.caption(id) || '';
    } catch {
      caption = '';
    }

    infos.push({ id, label, caption, args: null });
  }

  infos.sort((a, b) => a.id.localeCompare(b.id));
  return infos;
}

/**
 * Read the described arguments of one command and format them.
 *
 * A command without describedBy, or whose description throws, yields an
 * empty string.
 */
export async function describeCommand(
  commands: CommandRegistry,
  id: string
): Promise<string> {
  try {
    const description = await commands.describedBy(id);
    if (description && description.args) {
      return formatArgs(description.args);
    }
  } catch {
    // Command may not have describedBy implemented
  }
  return '';
}

/**
 * Collect the registered commands with their formatted arguments.
 *
 * Commands are described in batches so a large registry does not block the
 * browser in one long sequence of awaits.
 */
export async function collectCommandDescriptors(
  commands: CommandRegistry,
  batchSize = 50
): Promise<ICommandInfo[]> {
  const infos = collectCommands(commands);

  for (let i = 0; i < infos.length; i += batchSize) {
    const batch = infos.slice(i, i + batchSize);
    await Promise.all(
      batch.map(async info => {
        info.args = await describeCommand(commands, info.id);
      })
    );
  }

  return infos;
}
