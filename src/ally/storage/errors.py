"""Storage failures that application interfaces can report without adapter coupling."""


class DatabaseMigrationError(RuntimeError):
    """A safe, payload-free failure to initialize or upgrade a database."""
