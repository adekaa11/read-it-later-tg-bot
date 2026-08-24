"""
handlers/__init__.py — экспорт роутеров для подключения в main.py.
"""

from handlers import callbacks, commands, links

# Порядок важен: команды и коллбэки обрабатываются раньше,
# а роутер links — последним (fallback для сообщений со ссылками).
ALL_ROUTERS = [commands.router, callbacks.router, links.router]
