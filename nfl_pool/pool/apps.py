from django.apps import AppConfig


class PoolConfig(AppConfig):
    name = 'pool'

    def ready(self):
        import pool.models  # noqa: F401 — registers signals
