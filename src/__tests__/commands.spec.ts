import { formatArgs } from '../commands';

describe('formatArgs', () => {
  it('formats JSON Schema properties with their types', () => {
    expect(
      formatArgs({
        type: 'object',
        properties: {
          path: { type: 'string' },
          activate: { type: 'boolean' }
        }
      })
    ).toEqual('path: string, activate: boolean');
  });

  it('returns an empty string for an empty properties object', () => {
    expect(formatArgs({ type: 'object', properties: {} })).toEqual('');
  });

  it('returns an empty string for a value that is not an object', () => {
    expect(formatArgs(null)).toEqual('');
    expect(formatArgs(undefined)).toEqual('');
    expect(formatArgs('path')).toEqual('');
  });

  it('falls back to key names for a direct argument object', () => {
    expect(
      formatArgs({ path: {}, factory: {}, type: 'object', $schema: 'x' })
    ).toEqual('path, factory');
  });

  it('keeps a property name that has no type', () => {
    expect(formatArgs({ properties: { path: {} } })).toEqual('path');
  });

  it('ignores schema keys when there are no direct arguments', () => {
    expect(formatArgs({ type: 'object', $schema: 'x' })).toEqual('');
  });
});
