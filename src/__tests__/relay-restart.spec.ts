import type { JupyterFrontEnd } from '@jupyterlab/application';
import type { ISettingRegistry } from '@jupyterlab/settingregistry';
import type { CommandRegistry } from '@lumino/commands';

import { RelayClient } from '../relay';

interface IRelayProbe {
  relay: RelayClient;
  register: jest.Mock;
  get: jest.Mock;
}

/**
 * Build a client whose registration and pending read the test controls, so no
 * request reaches a server.
 */
function makeProbe(): IRelayProbe {
  const signal = () => ({ connect: jest.fn(), disconnect: jest.fn() });
  const client = new RelayClient({
    app: {} as unknown as JupyterFrontEnd,
    commands: { commandChanged: signal() } as unknown as CommandRegistry,
    settings: { changed: signal() } as unknown as ISettingRegistry.ISettings,
    registry: {} as ISettingRegistry
  });
  const register = jest.fn();
  const get = jest.fn(() => new Promise(() => {}));
  const relay = client as unknown as { _register: jest.Mock; _get: jest.Mock };
  relay._register = register;
  relay._get = get;
  return { relay: client, register, get };
}

describe('RelayClient.start', () => {
  it('starts the pending poll only after the first register resolves', async () => {
    const { relay, register, get } = makeProbe();
    let resolveRegister!: () => void;
    const registration = new Promise<void>(resolve => {
      resolveRegister = resolve;
    });
    register.mockReturnValue(registration);

    relay.start();
    await Promise.resolve();

    expect(register).toHaveBeenCalledTimes(1);
    expect(get).not.toHaveBeenCalled();

    resolveRegister();
    await registration;
    await Promise.resolve();

    expect(get).toHaveBeenCalledWith('pending');
  });

  it('starts the pending poll when the first register rejects', async () => {
    const { relay, register, get } = makeProbe();
    const registration: Promise<void> = Promise.reject(
      new Error('register failed')
    );
    registration.catch(() => {});
    // The client does not handle a rejection itself because the real
    // _register catches its own errors; attach a handler to the promise the
    // client derives from finally so the forced rejection stays quiet.
    const settled = registration.finally.bind(registration);
    (registration as unknown as { finally: typeof settled }).finally =
      callback => {
        const derived = settled(callback) as Promise<void>;
        derived.catch(() => {});
        return derived;
      };
    register.mockReturnValue(registration);

    relay.start();
    await registration.catch(() => {});
    await Promise.resolve();

    expect(get).toHaveBeenCalledWith('pending');
  });

  it('starts no pending poll when disposed before register resolves', async () => {
    const { relay, register, get } = makeProbe();
    let resolveRegister!: () => void;
    const registration = new Promise<void>(resolve => {
      resolveRegister = resolve;
    });
    register.mockReturnValue(registration);

    relay.start();
    relay.dispose();
    resolveRegister();
    await registration;
    await Promise.resolve();

    expect(get).not.toHaveBeenCalled();
  });
});
