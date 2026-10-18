/**
 * Configuration for Playwright using default from @jupyterlab/galata
 */
const path = require('path');

const baseConfig = require('@jupyterlab/galata/lib/playwright-config');

const PORT = process.env.JUPYTER_TEST_PORT || '8888';
const BASE_URL = `http://localhost:${PORT}`;
const GALATA_CONFIG = path.resolve(__dirname, 'galata-config');

module.exports = {
  ...baseConfig,
  // The tests share one Jupyter server and one browser relay, so they must
  // not run concurrently.
  workers: 1,
  fullyParallel: false,
  use: { ...baseConfig.use, baseURL: BASE_URL },
  webServer: {
    command: 'jlpm start',
    url: `${BASE_URL}/lab`,
    timeout: 120 * 1000,
    reuseExistingServer: false,
    env: {
      ...process.env,
      JUPYTER_CONFIG_PATH: GALATA_CONFIG
    }
  }
};
