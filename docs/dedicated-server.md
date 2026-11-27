# Running a dedicated server

The dedicated server is its own download for Linux, for x86, x64 and
arm64 machines (Oracle Cloud's free tier and Raspberry Pis included), and for
64-bit Windows. A new server walks you through its setup in its control
panel, and the Status tab says whether people can join. See
the [Chupathingy Dedicated Server](../server/README.md) page, with which
download fits your machine, a quick start, playlists, settings, Docker and
systemd.

## On a desktop

The game itself (Windows, Mac or Linux) still turns into a dedicated server
when `HALO_DEDICATED` names a playlist in its data folder, with no window:
handy to try a playlist on the computer you play on. It takes the server's
[settings](../server/docs/settings.md) and
[playlists](../server/docs/playlists.md). For a server that stays up, use the
server download.

## Bots

A server can have bots: players the server drives itself, so a game is
worth joining before anyone else is there.

| Setting | Default | What it does |
| --- | --- | --- |
| `HALO_BOTS` | `0` | This many bots in every game. |
| `HALO_BOTS_FILL` | `0` | Fill every game up to this many players with bots. A bot leaves when a person joins, and comes back when one leaves. `0` means `HALO_BOTS` bots, whoever joins. |
| `HALO_BOT_SKILL` | `5` | How good they are: `1` easy to `10` near perfect. |

The bots come in with the first person to join: the server doesn't play
games of bots alone, and a game ends 30 seconds after the last person
leaves it, bots or not. With bots, one person is enough for a team game.

A game the bots played in gets no carnage report on the site: the stats
there are for people.

The first game with bots on each map takes a few seconds longer to start,
while the server works out where the bots can go. To do that ahead of time
for every map, run `bake-navigation.cmd` (Windows), or start the game once
with `HALO_BAKE_NAVIGATION=all` (Linux and Mac): it writes a `navcache`
folder next to `maps` and quits. More in the
[port's README](../port/linux/README.md#baked-navigation).
