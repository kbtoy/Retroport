# Racial passives: bringing the stock races up to the new races' standard

The ported races each have three or four passives beside their active: Kul Tiran 4, Pandaren 4,
Mag'har 3, Earthen 4. Here is where the stock races stand on the server, and what retail 12.1.5 has
given each since 3.3.5. Read from `D:\AC`'s DBCs and the local retail install.

**Passives today** (in brackets: the elemental resistances, which do little at 80):

| Race | Passives on the server | Count | Without resistances |
|---|---|---|---|
| Human | Diplomacy, The Human Spirit, Sword Specialization, Mace Specialization, Perception | 5 | 5 |
| Orc | Hardiness, Axe Specialization, Command | 3 | 3 |
| Troll | Regeneration, Beast Slaying, Throwing Specialization, Bow Specialization, Da Voodoo Shuffle | 5 | 5 |
| Night Elf | Quickness, Wisp Spirit, Elusiveness, (Nature Resistance) | 4 | 3 |
| Dwarf | Gun Specialization, Mace Specialization, (Frost Resistance) | 3 | 2 |
| Tauren | Endurance, Cultivation, (Nature Resistance) | 3 | 2 |
| Gnome | Expansive Mind, Engineering Specialization, (Arcane Resistance) | 3 | 2 |
| Draenei | Heroic Presence, Gemcutting, (Shadow Resistance) | 3 | 2 |
| Undead | Underwater Breathing, (Shadow Resistance) | 2 | 1 |
| Blood Elf | Arcane Affinity, (Magic Resistance) | 2 | 1 |

**What retail added that 3.3.5 never had** - my recommendation is to add these, ported as the other
racials were (spell rows plus server scripts where needed), keeping every 3.3.5 racial as it is:

| Race | Add | What it does, in 3.3.5 terms | How |
|---|---|---|---|
| Undead | **Touch of the Grave** | attacks and damaging spells sometimes drain the target: Shadow damage, healed for the same | proc aura + its spell |
| Blood Elf | **Arcane Acuity** | +1% critical strike chance | plain aura |
| Dwarf | **Might of the Mountain** | critical strikes deal and heal 2% more | aura + a small script for healing crits |
| Tauren | **Brawn** | the same as the Dwarf's: crits deal and heal 2% more | as the Dwarf's |
| Gnome | **Nimble Fingers** | +1% haste (melee, ranged and spells) | plain auras |
| Night Elf | **Touch of Elune** | +1% haste at night, +1% critical strike by day (server time) | script on the day/night switch |
| Human | No Place Like Home (optional) | Hearthstone cooldown 5 minutes shorter (3.3.5 has no charges) | script |

That gives Undead and Blood Elf a third passive, and Dwarf, Tauren and Gnome a third without
counting resistances. Night Elf and Human go a step past.

**Left as they are:** Orc, Troll and Draenei. Retail gave them nothing new (only Blood Fury variants
and a reworded Heroic Presence). Orc and Troll already have three or more. Draenei would stay at two
plus Shadow Resistance; a third would have to be invented rather than ported, so only on your say.

**Notes**
- Retail also reworded some existing racials (Expansive Mind as maximum mana, Quickness with movement
  speed, The Human Spirit as secondary stats). I'd keep the 3.3.5 versions, which fit 3.3.5's stats.
- The added passives are small (1% or 2% each), on par with the new races' own.
- They live on the server, so they apply on every client. Their tooltips and spellbook entries need
  the client patch in each client that plays: the two x64 clients, and the main client only if you
  say so.
