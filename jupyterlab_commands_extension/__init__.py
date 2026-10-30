try:
    from ._version import __version__
except ImportError:
    # Fallback when using the package in dev mode without installing
    # in editable mode with pip. It is highly recommended to install
    # the package from a stable release or in editable mode: https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs
    import warnings
    warnings.warn("Importing 'jupyterlab_commands_extension' outside a proper installation.")
    __version__ = "dev"


def _jupyter_labextension_paths():
    return [{
        "src": "labextension",
        "dest": "@stellarshenson/jupyterlab-commands-extension"
    }]


def _jupyter_server_extension_points():
    return [{
        "module": "jupyterlab_commands_extension"
    }]


def _load_jupyter_server_extension(server_app):
    """Create the relay and register its HTTP handlers.

    Parameters
    ----------
    server_app: jupyterlab.labapp.LabApp
        JupyterLab application instance
    """
    from .handlers import RELAY_KEY, setup_route_handlers
    from .relay import Relay

    server_app.web_app.settings[RELAY_KEY] = Relay()
    setup_route_handlers(server_app.web_app)
    server_app.log.info(
        "Registered jupyterlab_commands_extension server extension"
    )
