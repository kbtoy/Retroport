"""Which Retroport Workbench this is: the edition for the 32-bit client (Ultra WoW 32-bit).

That client is Ultra WoW built as a 32-bit program from the same source as the x64 one, so it draws
retail's items itself too: Install puts retail's own items, mounts and their files straight into it
(``direct``). Nothing is converted, and nothing of another tool's - no backport kit, no WarcraftXL or
Equip Plus - is needed or downloaded.

It keeps its own settings and data folder, and its own port, so it runs beside the x64 edition.
"""

KEY = "32bit"
NAME = "Retroport Workbench 32-bit"
CLIENT_NAME = "the 32-bit client"
CLIENT_EXE = "WowClient32.exe"           # the game's program in the client folder Install goes into
PORT = 8337
# in %USERPROFILE%\.retroport: its settings, and the folder with its cache, basket and installs
SETTINGS_FILE = "workbench-32bit.json"
DATA_FOLDER = "workbench-32bit"
