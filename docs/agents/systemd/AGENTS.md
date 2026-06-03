# Agent prompt: install + background-run Tokdash

Goal: help the user install Tokdash and keep it running in the background for local dashboards.

## Questions to ask first
- OS: Linux (systemd) or macOS (launchd)?
- Bind + security: keep `127.0.0.1` (recommended) or expose on LAN (`0.0.0.0`, only if the user explicitly wants this)?
- Remote access: local-only, or do they want secure remote access via `tailscale serve`?
- Port: keep default `55423` or change due to conflicts?
- Install method: venv vs `pipx` vs system Python?
- Linux only: do they want the optional `/health` probe timer as a restart backstop?

## Procedure (do this, in order)
1. Install Tokdash (`pip install tokdash`) and record the **absolute path** of `tokdash` (`which tokdash`).
2. Verify it works in foreground: `tokdash serve --bind 127.0.0.1 --port 55423`, then open `http://127.0.0.1:55423/`.
3. Download and configure the service template with the correct **absolute** `tokdash` path.

   **Linux (systemd):**
   ```bash
   mkdir -p ~/.config/systemd/user
   TOKDASH_PATH=$(which tokdash)
   cat > ~/.config/systemd/user/tokdash.service << EOF
   [Unit]
   Description=Tokdash (local token & cost dashboard)
   After=network-online.target

   [Service]
   Type=simple
   ExecStart=$TOKDASH_PATH serve --bind 127.0.0.1 --port 55423 --no-open
   Restart=on-failure
   RestartSec=3
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=default.target
   EOF
   ```

   **macOS (launchd):**
   ```bash
   TOKDASH_PATH=$(which tokdash)
   cat > ~/Library/LaunchAgents/com.tokdash.tokdash.plist << EOF
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
     <key>Label</key>
     <string>com.tokdash.tokdash</string>
     <key>ProgramArguments</key>
     <array>
       <string>$TOKDASH_PATH</string>
       <string>serve</string>
       <string>--bind</string>
       <string>127.0.0.1</string>
       <string>--port</string>
       <string>55423</string>
       <string>--no-open</string>
     </array>
     <key>RunAtLoad</key>
     <true/>
     <key>KeepAlive</key>
     <true/>
     <key>StandardOutPath</key>
     <string>/tmp/tokdash.out.log</string>
     <key>StandardErrorPath</key>
     <string>/tmp/tokdash.err.log</string>
   </dict>
   </plist>
   EOF
   ```

4. Enable + start:
   - systemd: `systemctl --user enable --now tokdash`
   - launchd: `launchctl load -w ~/Library/LaunchAgents/com.tokdash.tokdash.plist`
5. Validate via API:
   - `curl 'http://127.0.0.1:55423/api/usage?period=today'`
6. Show where logs are:
   - systemd: `journalctl --user -u tokdash -f`
   - launchd: `/tmp/tokdash.out.log` and `/tmp/tokdash.err.log` (or whatever the plist sets)
7. Linux optional: if the user wants a watchdog-style backstop, install the health-probe timer from `docs/agents/systemd/health-probe/`:
   ```bash
   install -Dm644 docs/agents/systemd/health-probe/tokdash-health.service ~/.config/systemd/user/tokdash-health.service
   install -Dm644 docs/agents/systemd/health-probe/tokdash-health.timer ~/.config/systemd/user/tokdash-health.timer
   systemctl --user daemon-reload
   systemctl --user enable --now tokdash-health.timer
   ```
   If the service uses a non-default port, edit `TOKDASH_PORT` in the health-probe service or use a drop-in.
8. If the user wants remote/mobile access, ask if they want to run:
   - `tailscale serve --bg 55423`
   Keep Tokdash bound to `127.0.0.1`; avoid exposing `0.0.0.0` unless explicitly requested.

## Safety notes
- Default to `127.0.0.1` unless the user explicitly requests LAN exposure.
- Prefer `tailscale serve` over `0.0.0.0` for remote access.
- If the user asks for `0.0.0.0`, warn them that anyone on the LAN may be able to access the dashboard unless they add auth / firewall rules.

Reference: `https://github.com/JingbiaoMei/tokdash/blob/main/docs/agents/systemd/BACKGROUND_RUN.md`.
