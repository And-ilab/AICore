"""Legacy shim: use ``sufler.wsgi`` in new code."""
from sufler.wsgi import application

__all__ = ["application"]
