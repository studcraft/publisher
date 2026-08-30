# Local WordPress

A throwaway WordPress, in Docker, for testing publication without touching a live site.

The publisher's last stage talks to a real WordPress over its REST API. That stage is the
one part unit tests cannot fully cover — slugs, page hierarchy, post status and permalinks
are WordPress's behaviour, not ours. This harness makes that behaviour observable locally.

**Stock core, no plugins.** Nothing is installed on the site, because the publishing design
depends on nothing being installed. If something here ever needs a plugin to work, that is a
finding about the design, not a missing step in this README.

## Running it

```bash
docker compose up -d
./bootstrap.sh
```

- Site — <http://localhost:8080>
- Admin — <http://localhost:8080/wp-admin>, `admin` / `admin`
- Editor — `editor` / `editor`, for reviewing what is staged before it goes public
- Credentials for the publisher — `.env`, written by `bootstrap.sh`, git-ignored

Both commands are safe to re-run: `bootstrap.sh` checks before each step, so running it
again after a restart repairs the site rather than duplicating anything.

Port 8080 is the default. If it is taken:

```bash
WP_PORT=8090 docker compose up -d
WP_PORT=8090 ./bootstrap.sh
```

The port has to be given to both — WordPress stores its own URL in the database and serves
redirects from it, so the container and the installer must agree.

## Starting over

```bash
docker compose down -v
```

`-v` drops the volumes, which is the point: the database and the WordPress files go with
them, and the next `up` + `bootstrap.sh` gives a site with no history. Everything here is
disposable by design — never keep anything in this WordPress that is not reproducible from
the repository.

## The credentials are deliberately trivial

`admin` / `admin` on a container published to localhost only, with a disposable volume
behind it. A generated password here would be a secret from the person who needs to log in,
and would protect nothing. **Nothing in this directory is a model for the production site**,
which authenticates with an application password held in GitHub Actions secrets.

## What was verified here

Against stock `wordpress:latest`, by hand through WP-CLI:

- `/%postname%/` permalinks resolve with no Apache configuration of our own. WP-CLI's
  `Warning: Regenerating a .htaccess file requires special configuration` is harmless — the
  image already wrote a working `.htaccess`.
- A page slug submitted as `CORE-001` is stored lowercased, as `core-001`.
- Parent and child pages give `/core-rules/core-001/`.
- A `private` page returns `404` to an anonymous visitor and `200` once published, which is
  what the editors-only staging step relies on.
- `/core-rules/CORE-001/` also returns `200`, with a canonical link to the lowercase URL.
  That is MySQL's case-insensitive collation, not a WordPress guarantee.
