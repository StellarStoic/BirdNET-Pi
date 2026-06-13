# Tor Hosting Guide for BirdNET-Pi

This document explains how to make BirdNET-Pi remotely accessible through a Tor v3 onion service without opening an inbound router port.

## Overview

BirdNET-Pi can be exposed as a Tor hidden service (v3 onion address). When enabled, your BirdNET-Pi web interface becomes accessible via an `.onion` address that only works through Tor Browser or other Tor clients. The clearnet (regular HTTP) interface remains unchanged.

**Key Features:**
- One-click enable/disable from Advanced Settings UI
- Onion v3 address generation
- Stable onion address across disable/re-enable operations
- Explicit onion identity reset when needed


## Installation
**This Tor option has only been build and tested on the RPi3B+ (bookworm 64bit Lite)**
**I highly recommend using more powerful raspberry. birdnet-pi on cheap RPi5 2GB is working smoothly**


## Example Installation Workflow

0. **Prerequisites** before birdnetPi install for **rpi3b+** & **rpi 0 W2 only**
-  `sudo sed -i 's/CONF_SWAPSIZE=100/CONF_SWAPSIZE=2048/g' /etc/dphys-swapfile`
-  `sudo sed -i 's/#CONF_MAXSWAP=2048/CONF_MAXSWAP=4096/g' /etc/dphys-swapfile`
-  `sudo nano /etc/rc.local`
-  Paste this in the file:
```bash
sudo sh -c 'cat > /etc/rc.local << EOF
#!/bin/sh -e
#
# rc.local - executed at the end of each multiuser runlevel
#
# This script disables WiFi power saving for better performance

# Disable WiFi power saving

exit 0
EOF'
```
-  `sudo sed -i '/^exit 0/i sudo iw wlan0 set power_save off' /etc/rc.local`
-  `sudo chmod +x /etc/rc.local`
-  `sudo reboot`
-  Now proceed with normal installation

1. **Install BirdNET-Pi** (From fork that includes Tor currently! `curl -fsSL https://raw.githubusercontent.com/StellarStoic/BirdNET-Pi/main/newinstaller.sh | bash` )


## Enabling Tor Hosting

### Via Web UI (Easiest)

1. Open BirdNET-Pi in your browser
2. Go to **Settings → Advanced Settings**
3. Find the **Tor Hosting** section
4. Check the box: **"Host this BirdNET-Pi on Tor"**
5. Click **"Update Settings"**
6. Wait up to 60 seconds for the onion address to be generated
7. Reload the page; the onion address will appear
8. If you think nothing has happened, refresh the page


### Usefull commands

(Ensure Tor is running: `systemctl status tor`)

```bash
# Enable
sudo /usr/local/bin/update_tor_service.sh enable

# Disable
sudo /usr/local/bin/update_tor_service.sh disable

# Restart an enabled onion service without changing its address
sudo /usr/local/bin/update_tor_service.sh restart

# Deliberately delete the old keys and generate a new onion address
sudo /usr/local/bin/update_tor_service.sh reset
```

Both commands will output the onion address (if enabling) or confirmation (if disabling).

## Using Your Onion Address

Once enabled, you can access your BirdNET-Pi via Tor:

1. **Install Tor Browser** (https://www.torproject.org/download/#browser)
2. **Open Tor Browser**
3. **Visit your onion address** (e.g., `http://example1234567890abcdef.onion`)

The address appears in the **Tor Hosting** section under Advanced Settings, and is stored in `/etc/birdnet/birdnet.conf` as `TOR_ONION`.

## Security & Privacy Considerations

### Benefits of Tor

- **Private routing:** Visitors and the BirdNET-Pi host do not make a direct network connection
- **Censorship Resistance:** Accessible from countries that block your domain/IP
- **No Domain Needed:** No need for DNS or public IP registration
- **Encryption:** All Tor traffic is encrypted end-to-end
- **Price:** FREE

### Limitations

- **Slower:** Tor routes through multiple nodes, adding latency (typically 1-3 seconds slower)
- **Public application data:** BirdNET-Pi pages, recordings, metadata, hostnames, and linked resources can still reveal identifying information
- **Existing LAN/clearnet access:** Enabling Tor does not disable BirdNET-Pi's normal network interface
- **Address secrecy is not access control:** Anyone who learns the onion address can connect; configure BirdNET-Pi authentication for sensitive installations
- **Onion identity backup:** The private keys in `/var/lib/tor/birdnet_hidden_service/` control the address and must remain secret

### Best Practices

1. **Keep Tor Updated:**
   ```bash
   sudo apt-get update && sudo apt-get upgrade tor
   ```
   Tor 0.4.8 or newer supports proof-of-work protection for onion services. BirdNET-Pi enables it automatically when the installed Tor build supports it. Check with `tor --version` and use a currently supported Raspberry Pi OS release.

2. **Monitor Tor Logs:**
   ```bash
   sudo journalctl -u tor -f
   ```

3. **Firewall:** Tor makes outbound connections and does not require inbound port forwarding. Avoid narrow outbound port rules because relay ports vary.

4. **Protect the dashboard:** Use BirdNET-Pi authentication. An onion service encrypts transport and hides network locations, but it does not authenticate visitors by default.

## Troubleshooting

### Onion Address Not Showing

**Symptom:** You enabled Tor but no onion address appears

**Solution:**
1. Check Tor service status:
   ```bash
   sudo systemctl status tor
   ```
2. Check for errors in the log file (created during enable):
   ```bash
   tail -20 /tmp/tor_service_enable_*.log
   ```
3. Ensure the hidden service directory exists:
   ```bash
   sudo ls -la /var/lib/tor/birdnet_hidden_service/
   ```

### Cannot Connect via Onion Address

**Symptom:** Onion address appears but Tor Browser cannot reach it

**Solution:**
1. Check that the clearnet BirdNET-Pi is accessible (Tor proxies the clearnet service)
2. Verify Tor is still running:
   ```bash
   sudo systemctl status tor
   ```
3. Check Caddy/webserver logs:
   ```bash
   sudo journalctl -u caddy -n 20
   ```
4. Try accessing from the clearnet first to ensure BirdNET-Pi is working
5. Restart Tor:
   ```bash
   sudo systemctl restart tor
   ```

### Permission Denied Errors

**Symptom:** `Permission denied` when running the helper script

**Solution:**
- Always run with `sudo`:
  ```bash
  sudo /usr/local/bin/update_tor_service.sh enable
  ```
- Or from the web UI (which handles sudo internally)

### Non-Debian/Non-Systemd Systems

This guide assumes you are running BirdNET-Pi on Raspberry Pi OS (Debian-based).

## Configuration Files

### Tor Configuration

- **Service Config:** `/etc/tor/torrc.d/birdnet.conf`
  - Defines the hidden service directory and port mappings
  - Auto-generated when you enable Tor

### BirdNET-Pi Config

- **Config File:** `/etc/birdnet/birdnet.conf`
  - `TOR_ENABLED=1` or `0` (whether the BirdNET onion service is active)
  - `TOR_ONION="http://example1234567890abcdef.onion"` (your onion address)

### Tor Data Directory

- **Hidden Service Dir:** `/var/lib/tor/birdnet_hidden_service/`
  - `hostname` – Your onion address (readable by root only)
  - `hs_ed25519_secret_key` – Your onion service private identity key (DO NOT SHARE!)
  - Owned by the `debian-tor` user

## Advanced Usage

### Manual Tor Configuration

If you need custom Tor settings, edit `/etc/tor/torrc.d/birdnet.conf`:

```bash
sudo nano /etc/tor/torrc.d/birdnet.conf
```

Then restart:
```bash
sudo systemctl restart tor
```

### Exposing Additional Ports

To expose other services (e.g., SSH, database) via Tor, add them to the config:

```bash
cat <<EOF | sudo tee -a /etc/tor/torrc.d/birdnet.conf

# Additional hidden service for SSH (example)
HiddenServiceDir /var/lib/tor/birdnet_ssh
HiddenServiceVersion 3
HiddenServicePort 22 127.0.0.1:22
EOF

sudo systemctl restart tor
```

Then read the new onion address:
```bash
sudo cat /var/lib/tor/birdnet_ssh/hostname
```

### Permanent Onion Address

Your onion address is tied to the private keys in `/var/lib/tor/birdnet_hidden_service/`. Normal disable/re-enable operations preserve this directory and address. The `reset` action permanently deletes the identity and creates a new address.

## Getting Help

- **Tor Project:** https://www.torproject.org/
- **Tor Browser:** https://www.torproject.org/download/
- **BirdNET-Pi Repo:** https://github.com/Nachtzuster/BirdNET-Pi

For issues with the helper script, check:
```bash
/tmp/tor_service_*.log
sudo journalctl -u tor
sudo journalctl -u caddy
```

**Last Updated:** June 2026
**BirdNET-Pi Tor Integration v1.1**
