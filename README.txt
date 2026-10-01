Albion Flips - market flip finder for Albion Online
Americas server only. Windows only (no Mac or Linux).

HOW TO RUN
1. Right-click the zip and choose "Extract All". Put the folder on your Desktop or in
   Documents. Avoid Program Files - Windows blocks the app from saving settings there.
   Don't run the app from inside the zip - it won't find watchlist.txt that way.
2. Open the extracted folder and double-click AlbionFlips.exe.
   Keep AlbionFlips.exe and watchlist.txt in the same folder.
3. If Windows shows "Windows protected your PC", click "More info", then "Run anyway".
   (The app isn't code-signed, so Windows warns about it the first time.)
4. If your antivirus deletes or quarantines AlbionFlips.exe: that's a known false alarm
   for small self-packaged apps like this one. Restore it from your antivirus
   quarantine and allow it, or skip the tool if you'd rather not.
5. Give it a few seconds to open. The first price load for the full list takes about
   15 seconds; after that each refresh takes about 6.

WHAT IT SHOWS
- Items you could buy with a buy order and resell with a sell order in one city.
- Profit/unit already takes off the fees: 2.5% setup on each order plus sales tax
  (4% with Premium, 8% without - untick "Premium" if you don't have it, or every
  profit number will be too high).
- Est. profit/day assumes you can fill about 10% of that item's daily sales.
- Age = how old the price is. Prices come from the Albion Online Data Project,
  which is crowd-sourced, so they can be hours old. Always check in game first.
- Fewer rows than items in your list is normal. An item only shows when the city has
  both a buy order and a sell order for it right now.

YOUR ITEM LIST
- watchlist.txt comes loaded with food and potions plus every crafting material:
  ore, bars, wood, planks, fiber, cloth, hide, leather, stone, blocks (all tiers and
  enchants), runes/souls/relics/shards, crops, herbs, animal products, cooking
  ingredients and fish. It's grouped into sections so you can trim it.
- Edit it in Notepad: one item name per line, exactly as shown in game.
  Add .1 / .2 / .3 / .4 for enchants (Beef Stew .1, Steel Bar .4). Resources also
  work by their full in-game name (Uncommon Steel Bar = Steel Bar .1).
- Delete a line or put # in front of it to skip it. Save, then hit Refresh in the app.
- Misspelled lines are skipped, and the app shows a yellow bar listing them so you
  can fix the spelling.
- The app uses the watchlist when Scope says "Watchlist (watchlist.txt)" (the default).
  The bottom-right corner shows how many items it loaded.
- If it says "watchlist.txt not found": the file has to sit next to AlbionFlips.exe
  and be named exactly watchlist.txt (Windows hides extensions, so Notepad can save it
  as watchlist.txt.txt). Editing the file that came in the zip avoids this.
- Shorter lists refresh faster.
- The Scope menu can also scan whole categories (consumables, refined resources, etc.).

OPTIONS
- Keep on top: pins the window over other windows. Off by default.
- All columns: shows live bid/ask, 7-day average and capital needed.
- Your settings are saved in settings.json next to the app when you close it.

Uses only the public market API. It does not touch the game client.
