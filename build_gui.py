"""PyInstaller entry point for the GUI. Not meant to be run directly by
users -- see README's "Taşınabilir sürüm (tek .exe)" section for the
build command that uses this file.
"""

from data_recovery.gui import main

if __name__ == "__main__":
    main()
