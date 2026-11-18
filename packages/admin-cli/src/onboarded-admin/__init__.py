"""
onboarded_admin — ``ob-admin``, the Onboarded admin CLI.

Modules:
    cli       argument parsing, command dispatch, exit-code contract (entry point: ``main``)
    backends  HttpBackend (REST API, stdlib urllib) and LocalBackend (reads the repo
              through onboarded_api's service layer); both raise ``CliError``
    render    human-readable output (tables, colour only on a TTY, honours NO_COLOR)

Run as ``ob-admin`` (installed) or ``python -m onboarded_admin``.
See packages/admin-cli/README.md.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
