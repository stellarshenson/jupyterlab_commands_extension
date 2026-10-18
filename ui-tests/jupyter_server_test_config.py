"""Server configuration for integration tests.

!! Never use this configuration in production because it
opens the server to the world and provide access to JupyterLab
JavaScript objects through the global window variable.
"""
import os
from tempfile import mkdtemp

from jupyterlab.galata import configure_jupyter_server

configure_jupyter_server(c)

# `or`, not a get() default: an exported-but-empty value must fall back.
c.ServerApp.port = int(os.environ.get("JUPYTER_TEST_PORT") or "8888")
c.LabApp.user_settings_dir = mkdtemp(prefix="galata-settings-")

# The container has no writable trash directory, so send2trash fails and every
# Galata teardown DELETE answers 400. Deleting the fixture directly avoids it.
# The concrete class section is set as well because the image's
# jupyter_lab_config.py sets AsyncLargeFileManager.delete_to_trash = True, and
# traitlets applies the subclass section after the parent section.
c.ContentsManager.delete_to_trash = False
c.AsyncLargeFileManager.delete_to_trash = False

# Uncomment to set server log level to debug level
# c.ServerApp.log_level = "DEBUG"
