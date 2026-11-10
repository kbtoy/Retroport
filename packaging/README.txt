Retroport Workbench 32-bit
==========================

Browse retail World of Warcraft's items, transmog sets and mounts in 3D, pick what you want, and
install them into the 32-bit 3.3.5 client (Ultra WoW 32-bit) - and the SQL for your AzerothCore
server. That client draws retail's items itself, so nothing is converted: Install puts retail's own
models, textures and tables into the client as they are. No other tool is downloaded or run.


Start
-----
1. Unpack this whole folder anywhere. Keep runtime\ and app\ next to the .exe.
2. Run "Retroport Workbench 32-bit.exe". It opens in a window of its own; closing the window closes it.
   (Windows may say the program is from an unknown publisher - it isn't code-signed. Choose
   "More info", then "Run anyway".)
3. The first time, Settings opens: choose the 32-bit client's folder (the one with WowClient32.exe),
   and set Retail items to your own retail install (with the WoWDBDefs definitions and the
   community listfile) - Install reads retail's items and files from there.
4. Pick items, sets and mounts (+), look them over in the Basket, give them stats in Stats (item
   level, classes, stats, sockets...), then Install.


What it needs
-------------
- Windows 10 or 11. Its window is Microsoft Edge's app mode (Edge comes with Windows).
- The 32-bit 3.3.5 client (WowClient32.exe): Ultra WoW built as a 32-bit program.
- Your own retail install (World of Warcraft, the live game), WoWDBDefs' definitions folder
  (https://github.com/wowdev/WoWDBDefs) and the community listfile
  (https://github.com/wowdev/wow-listfile). Browsing works from wago.tools before those are set.


Where it keeps things
---------------------
  %USERPROFILE%\.retroport\workbench-32bit.json     your settings
  %USERPROFILE%\.retroport\workbench-32bit\         its cache, your basket, its installs and their backups, its log

Install backs up the patch it replaces in your client; Undo puts it back. It never runs SQL
against your database: it shows the item SQL for you to apply.


Not affiliated with or endorsed by Blizzard Entertainment. It ships no Blizzard assets: game data
is read at run time from wago.tools or your own game installs, for your own use. World of
Warcraft and its assets are trademarks and copyright of Blizzard Entertainment.
