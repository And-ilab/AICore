"""Legacy shim: use ``sufler.asgi`` in new code."""
from sufler.asgi import application

__all__ = ["application"]
