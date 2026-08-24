from .callbacks import router as callbacks_router
from .commands import router as commands_router
from .common import router as common_router
from .links import router as links_router

ALL_ROUTERS = [
    callbacks_router,
    commands_router,
    common_router,
    links_router,
]
