Worldwalker RPG — Linux / NAS Server Deployment
================================================

WHAT THIS IS
------------
This is the raw game (Flask backend + browser frontend), packaged to run
headless on Linux via Docker — no desktop window, no pywebview. You reach it
from any browser on the network instead.

IMPORTANT: THIS IS NOT SHARED MULTIPLAYER
------------------------------------------
Worldwalker RPG is built as a single-player game: one running instance holds
ONE shared game state (one character, one save, one AI conversation). If
several people connect to the SAME running instance at the same time, they
are all looking at and controlling the SAME character — not each playing
their own campaign.

To let several people each play their own independent game, run one
CONTAINER PER PERSON, each on its own port with its own private data folder.
That's what docker-compose.yml sets up: three example player instances,
each fully isolated from the others (separate saves, separate AI settings,
separate everything). Copy the block for more players.

HOW TO RUN IT
-------------
1. Install Docker (and Docker Compose) on the NAS if it isn't already —
   most NAS platforms (Synology Container Manager, QNAP Container Station,
   Unraid, TrueNAS apps, etc.) can build/run a docker-compose.yml directly.
2. Copy this whole folder onto the NAS.
3. From that folder, run:
       docker compose up -d --build
   This builds the image once and starts 3 isolated player containers,
   listening on host ports 5001, 5002, 5003.
4. Each player opens a browser to:
       http://<nas-ip-address>:5001/    (player 1)
       http://<nas-ip-address>:5002/    (player 2)
       http://<nas-ip-address>:5003/    (player 3)
   <nas-ip-address> is the NAS's address on your local network (e.g.
   192.168.1.50) — find it in the NAS's network settings.

ADDING MORE PLAYERS
--------------------
Easiest: regenerate the compose file instead of hand-editing it —
    python3 generate-compose.py 5
rewrites docker-compose.yml for 5 players on ports 5001-5005 (pass a second
number to change the starting port, e.g. `python3 generate-compose.py 3 6000`
for ports 6001-6003). Then run `docker compose up -d --build`.

Or by hand: duplicate one of the service blocks in docker-compose.yml, give
it a new container_name, a new host port, and a new data folder, then run
`docker compose up -d --build` again.

RESOURCE LIMITS
---------------
Each player container is capped at 1 GB RAM / 1 CPU (the `mem_limit` and
`cpus` lines in docker-compose.yml) so one busy session can't starve the
NAS for everyone else's game or its other services. Raise or lower these
to fit what the NAS can spare — e.g. `mem_limit: 512m` on a smaller NAS, or
`cpus: 2.0` if it's mostly idle otherwise.

OPTIONAL LOGIN (RECOMMENDED SINCE THE PORTS ARE FORWARDED TO THE INTERNET)
---------------------------------------------------------------------------
By default there's no login — anyone who reaches the port can play. Since
these ports are forwarded through the router, that means the raw internet,
not just your LAN: search-engine-style bots that scan for open ports could
stumble onto it even though you're not advertising the address anywhere.
For a close-friends-only game that's a low-odds risk, but the fix is cheap,
so it's worth turning on.

To require a login for a player's instance, uncomment and set both lines
in their service block in docker-compose.yml:
    environment:
      - AUTH_USER=player1
      - AUTH_PASS=some-password-you-choose
Give each player their own username/password (or share one set across all
of them if that's simpler). Run `docker compose up -d --build` to apply.
Anyone opening that player's URL will get a browser login prompt before
seeing the game. Leaving both lines commented out (the default) disables
auth for that instance.

This is deliberately simple (plain HTTP basic auth, no HTTPS) — good enough
to keep out random internet scanners among trusted friends, not a
substitute for real access control if this were ever opened up more
broadly.

BACKING UP SAVES
----------------
Run `./backup.sh` (or point the NAS's task scheduler at it, e.g. nightly)
to tar up every player's ./data folder into backups/worldwalker_data_<date
+time>.tar.gz. It automatically prunes backups older than 14 days. Restoring
just means untarring the one you want back over the data/ folder while the
containers are stopped.

TROUBLESHOOTING — A CONTAINER KEEPS RESTARTING / "OPENS AND CLOSES"
---------------------------------------------------------------------
First, see what's actually happening — the real reason is always in the
logs:
    docker compose logs worldwalker-player1
(swap the container name for whichever one is misbehaving).

The most common cause: the container crashes the instant it starts because
it can't write to its own data folder (./data/playerN), usually because the
NAS's Docker setup mounted that folder with different ownership than the
user the container runs as. This Dockerfile already works around it (it
force-fixes permissions on the mounted folder every time the container
starts), but if you're seeing this on a build from before that fix, or the
workaround doesn't apply to your NAS's setup, running:
    chmod -R 777 ./data
on the host, then `docker compose up -d --build` again, resolves it in
almost every case. This is fine for a private game server; it wouldn't be
an appropriate fix for something handling real secrets.

If the logs show something else entirely, that's the thing to act on —
don't guess further than what the log actually says.

EACH PLAYER NEEDS THEIR OWN AI SETUP
--------------------------------------
Nothing is pre-configured. The first time each player opens their instance,
they need to go into "AI & Portrait Setup" inside the game and enter either:
  - a cloud API key (OpenAI-compatible), or
  - the address of a local model server reachable from the NAS.
This is per-container — configuring one player's instance does not affect
any other player's. If you want everyone sharing one paid API key, you'd
enter the same key in each instance yourself; be aware that means every
player's usage bills to that one key, and cost scales with how many people
are actively playing at once.

SECURITY — READ BEFORE EXPOSING THIS TO THE INTERNET
-------------------------------------------------------
There is no login, password, or access control of any kind. Anyone who can
reach a given port can play that instance, read/change its save, and burn
through whatever API key is configured in it.
  - Safe: running this only on your home/local network, where only people
    you already trust can reach the NAS at all.
  - Risky: forwarding these ports through your router to the public
    internet. Do this only if you understand that means literally anyone
    who finds the address can use it — there is nothing in the app itself
    stopping them.
If you do want outside friends to connect over the internet, look into
putting the NAS behind a VPN (e.g. Tailscale/WireGuard) so only invited
devices can reach it at all, rather than opening the ports to the world.

PERSISTENCE
-----------
Each player's save games, settings, and AI-generated portraits live under
./data/playerN on the NAS's own disk (mounted into the container as /data).
Stopping, restarting, or rebuilding the container does not lose this data —
only deleting that folder would.

FILES IN THIS PACKAGE
----------------------
  backend/, frontend/, assets/, music/   - the game itself
  server.py                              - headless entry point (no pywebview)
  Dockerfile                             - builds the container image
  docker-compose.yml                     - example: 3 isolated player instances
  generate-compose.py                    - regenerates docker-compose.yml for N players
  backup.sh                              - tars up all players' save data
  requirements-server.txt                - the one Python dependency (Flask)
