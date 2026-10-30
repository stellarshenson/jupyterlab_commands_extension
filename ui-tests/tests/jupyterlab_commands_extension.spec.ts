import { expect, test } from '@jupyterlab/galata';

/**
 * The name of the LabIcon assigned to the reference tab title. The tab DOM
 * carries it as the data-icon attribute of the rendered svg.
 */
const DOCUMENT_ICON = 'ui-components:text-editor';

/**
 * Don't load JupyterLab webpage before running the tests.
 * This is required to ensure we capture all log messages.
 */
test.use({ autoGoto: false });

async function readAllowedCommands(page: any): Promise<string[]> {
  return page.evaluate(async () => {
    const registry = await (window as any).galata.getPlugin(
      '@jupyterlab/apputils-extension:settings'
    );
    const settings = await registry.load(
      '@stellarshenson/jupyterlab-commands-extension:plugin'
    );
    return settings.composite.allowedCommands;
  });
}

test('should emit an activation console message', async ({ page }) => {
  const logs: string[] = [];

  page.on('console', message => {
    logs.push(message.text());
  });

  await page.goto();

  expect(
    logs.filter(
      s =>
        s ===
        'JupyterLab extension @stellarshenson/jupyterlab-commands-extension is activated!'
    )
  ).toHaveLength(1);
});

test('should show the document icon and keep an added command after reload', async ({
  page
}) => {
  await page.goto();

  await page.evaluate(async () => {
    const app = (window as any).jupyterapp;
    await app.commands.execute('jupyterlab-commands-reference:open');
  });

  const tab = page.getByRole('tab', { name: 'Commands Reference' });
  await expect(tab).toBeVisible();
  // Fails if widget.title.icon stops being textEditorIcon: the tab then shows
  // no svg, or an svg whose data-icon names a different icon.
  await expect(
    tab.locator(`.lm-TabBar-tabIcon svg[data-icon="${DOCUMENT_ICON}"]`)
  ).toBeVisible();

  const addButton = page
    .locator('button.jp-CommandsReferenceWidget-add')
    .filter({ hasText: 'Add to command executor' })
    .first();
  await expect(addButton).toBeVisible();
  const commandId = (await addButton.getAttribute('data-command-id')) as string;
  expect(commandId).toBeTruthy();

  await addButton.click();
  await expect(
    page.locator(`button[data-command-id="${commandId}"]`)
  ).toHaveText('Added');
  expect(await readAllowedCommands(page)).toContain(commandId);

  // Fails if addAllowedCommand does not persist through settings.set: the
  // fresh page then reads the schema default and offers the Add button again.
  await page.goto();
  await page.evaluate(async () => {
    const app = (window as any).jupyterapp;
    await app.commands.execute('jupyterlab-commands-reference:open');
  });
  await expect(
    page.getByRole('tab', { name: 'Commands Reference' })
  ).toBeVisible();
  await expect(
    page.locator(`button[data-command-id="${commandId}"]`)
  ).toHaveText('Added');
  await expect(
    page.locator(`button[data-command-id="${commandId}"]`)
  ).toBeDisabled();
  expect(await readAllowedCommands(page)).toContain(commandId);
});

test('should show the allowedCommands array in the settings editor', async ({
  page
}) => {
  await page.goto();

  await page.evaluate(async () => {
    const app = (window as any).jupyterapp;
    await app.commands.execute('settingeditor:open', {});
  });

  const entry = page.locator(
    '.jp-PluginList-entry[data-id="@stellarshenson/jupyterlab-commands-extension:plugin"]'
  );
  await expect(entry).toBeVisible({ timeout: 30000 });
  await entry.click();

  const editor = page.locator('.jp-SettingsPanel');
  await expect(editor).toBeVisible({ timeout: 30000 });
  // Fails if schema/plugin.json stops declaring allowedCommands as an array,
  // or if the schema is no longer shipped to the settings registry.
  await expect(editor).toContainText('Allowed commands');
  const array = editor.locator('.jp-arrayFieldWrapper');
  await expect(array).toBeVisible();

  const values = await array
    .locator('input')
    .evaluateAll(inputs =>
      inputs.map(input => (input as HTMLInputElement).value)
    );
  expect(values).toContain('docmanager:open');
  expect(values).toContain('apputils:notify');
});
