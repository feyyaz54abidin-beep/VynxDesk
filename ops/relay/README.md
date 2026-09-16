# VynxDesk relay and rendezvous server

This stack provides the production rendezvous service (`hbbs`) and relay service
(`hbbr`) for VynxDesk clients. Deploy it on a Linux VPS with a static public IP.

## Before deployment

1. Choose a public DNS hostname for the VPS and create its record before
   setting `VYNX_RELAY_HOST`.
2. Allow TCP ports 21115 through 21119 and UDP port 21116 through the VPS and
   cloud firewalls.
3. Copy `.env.example` to `.env`, set the final public hostname, and choose a
   tested container image pinned to an immutable digest before customer rollout.
4. Restrict access to the `data` directory. It contains `id_ed25519`, the private
   rendezvous identity key. Do not put that file in a client package or source archive.

## Start and identify the server

```sh
docker compose up -d
docker compose ps
docker compose exec hbbs cat /root/id_ed25519.pub
```

The final command prints the public key that belongs in the desktop build. Build
the client only after both values below are final:

```powershell
$env:VYNXDESK_RENDEZVOUS_SERVER = '<production relay hostname>'
$env:VYNXDESK_RENDEZVOUS_PUB_KEY = '<public key printed by hbbs>'
```

The hostname and public key are a matched pair. Changing the server identity
after customers are deployed requires a controlled client release, so back up the
`data` directory securely before upgrades.

## Operations

- Check status with `docker compose ps` and service logs with `docker compose logs --tail=200`.
- Back up `data/id_ed25519` before host moves or container image changes.
- Keep only the listed ports public. Do not expose Docker management ports.
- Test direct and relayed sessions from separate networks before assigning the
  endpoint to a customer release.
