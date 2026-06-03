# Tokdash systemd health-probe backstop

An **optional** watchdog that restarts Tokdash if it stops answering `/health`.

## Why

Tokdash serves expensive usage requests on a bounded worker pool. The built-in
resilience fixes (single-flight caching, a heavy-compute cap, async liveness
handler, and uvicorn backpressure) make overload hangs unlikely, but this timer is
a small operational backstop: it turns an "alive but wedged" state into automatic
recovery.

`/health` is served on the asyncio event loop and never needs a worker thread, so
it should keep answering while workers are busy.

## Requirements

- Tokdash already running as a **user** service named `tokdash.service`
  (`systemctl --user`), and `curl` on `PATH`.
- If your service listens on a non-default port, edit `Environment=TOKDASH_PORT=`
  in `tokdash-health.service` (default `55423`).

## Install

Run from the repository root:

```sh
install -Dm644 docs/agents/systemd/health-probe/tokdash-health.service ~/.config/systemd/user/tokdash-health.service
install -Dm644 docs/agents/systemd/health-probe/tokdash-health.timer ~/.config/systemd/user/tokdash-health.timer
systemctl --user daemon-reload
systemctl --user enable --now tokdash-health.timer
```

Verify and watch:

```sh
systemctl --user list-timers tokdash-health.timer
journalctl --user -u tokdash-health.service -f
```

## Avoiding restart loops

So a genuinely broken service does not restart-flap forever, cap restarts on the
**main** `tokdash.service` (not this probe), e.g. via a drop-in:

```sh
systemctl --user edit tokdash.service
```

```ini
[Unit]
StartLimitIntervalSec=300
StartLimitBurst=5
```

## Uninstall

```sh
systemctl --user disable --now tokdash-health.timer
rm ~/.config/systemd/user/tokdash-health.{service,timer}
systemctl --user daemon-reload
```

## Test it

Simulate a wedge by pausing the service and confirm the timer restarts it after
the probe interval plus retry window:

```sh
kill -STOP "$(systemctl --user show -p MainPID --value tokdash.service)"
journalctl --user -u tokdash-health.service -n 10
```

If it does not restart for any reason, resume the process manually:

```sh
kill -CONT "$(systemctl --user show -p MainPID --value tokdash.service)"
```
