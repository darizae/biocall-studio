"""Single installed-wheel CLI entrypoint for the GUI and every private worker."""

from multiprocessing import freeze_support

# Required when the scientific runtime creates subprocesses in a frozen app.
freeze_support()

from biocall_studio.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
