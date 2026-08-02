# TAILER systemd service

> Validation checkpoint (2026-08-02): the unit and controller contract passed structural review, but this service has not yet been started on a real systemd/cgroup host because the available WSL1 environment does not provide one.

The unit manages the complete Docker Compose stack as one boot service. It uses
`/opt/tailer` as a stable deployment path because systemd does not expand shell
variables in `WorkingDirectory` or executable paths.

## Install

Install or symlink this repository at `/opt/tailer`, then create its environment
file before enabling the service:

~~~bash
sudo ln -s /absolute/path/to/Tailer /opt/tailer
cd /opt/tailer
sudo cp .env.example .env
sudo chmod 600 .env
sudo chmod +x tailer.sh
sudo install -m 0644 deploy/systemd/tailer.service /etc/systemd/system/tailer.service
sudo systemctl daemon-reload
sudo systemctl enable --now tailer.service
~~~

The unit invokes `/bin/bash` explicitly, so its service lifecycle does not
depend on Git preserving the script's executable bit. The `chmod` remains useful
for direct `./tailer.sh ...` operation.

Use a directory copy instead of a symlink when `/opt/tailer` should be an
independent deployment. If another path is required, update `WorkingDirectory`,
`ExecStart`, `ExecReload`, and `ExecStop` together before installing the unit.

Compose automatically reads `/opt/tailer/.env`; the file is deliberately not a
systemd `EnvironmentFile`, because Compose and systemd parse environment files
differently. Replace the development secrets in that file before deployment.
For a real-provider route, configure the versioned
`TAILER_CREDENTIAL_ENCRYPTION_KEYS` JSON registry and
`TAILER_CREDENTIAL_ACTIVE_KEY_VERSION` there with mode `0600`; never commit the
keyring. Keep every version referenced by an existing credential row. Do not put
an upstream OpenAI API key in this file: submit a disposable key through the
metadata-only admin credential API after the service is ready.

Backend startup automatically upgrades through Alembic head `0003`, including
`provider_credentials` and `model_configs`, before seeding and serving. The
The OpenAI adapter has mocked-upstream success coverage and a live Compose
connection-failure probe. Neither a successful disposable real-OpenAI smoke nor
revision-`0003` operation under this systemd unit has been verified. Compose
validation outside systemd does reach `0003` and exercises the adapter's
sanitized failure path. The validation caveat at the top therefore still
applies.

## Operate

~~~bash
sudo systemctl status tailer.service
sudo systemctl restart tailer.service
sudo systemctl stop tailer.service
sudo journalctl -u tailer.service
cd /opt/tailer && sudo ./tailer.sh logs
~~~

This system-level unit uses the host Docker daemon and therefore normally runs as
root. A non-root or rootless Docker installation needs a site-specific `User`,
Docker socket environment, and dependency override. The service is `oneshot`
with `RemainAfterExit` because Docker Compose detaches the containers; systemd
starts and stops the stack but does not supervise each container process.
