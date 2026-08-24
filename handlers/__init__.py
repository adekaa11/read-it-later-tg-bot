from . import callbacks, commands, common, links

ALL_ROUTERS = [r.router for r in (callbacks, commands, common, links) if hasattr(r, 'router')]
