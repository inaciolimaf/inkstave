# Inkstave infrastructure assets

`infra/` holds infrastructure and packaging assets: container build files,
docker-compose overrides, the nginx reverse-proxy config, CI helpers, the
Tectonic package set, and database init scripts. Most of these arrive in later
specs (notably the Docker/production spec, 56).

At spec 01 it contains only this README and a `postgres/` directory reserved
for Postgres init scripts that later specs may add.
