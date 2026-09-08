"""Process-level edition selection. Shared rules never select an AI provider."""
import os

MODE = os.environ.get('WORLDWALKER_MODE', 'main').strip().lower()
if MODE not in {'main', 'offline'}:
    raise ValueError('WORLDWALKER_MODE must be main or offline.')

def offline_enabled():
    return MODE == 'offline'
