"""Offline entry point into the same desktop launcher and game engine."""
import os
os.environ['WORLDWALKER_MODE'] = 'offline'
from launcher import main

if __name__ == '__main__':
    main()
