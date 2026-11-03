"""Prints a one-time login link for the admin page (valid 3 minutes). Run as the service user:
   runuser -u companion -- /opt/companion/venv/bin/python -m tools.admin_link"""
from app import config
from app.admin import new_code

print(f"http://{config.LAN_IP}:{config.PORT}/admin/login?code={new_code()}")
