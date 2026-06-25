#!/usr/bin/env bash
# Manage the BirdNET-Pi Tor onion service without disturbing other Tor services.
# Usage: update_tor_service.sh enable|disable|restart|reset

set -Eeuo pipefail
umask 077

ACTION="${1:-}"
TOR_USER="debian-tor"
TORRC="/etc/tor/torrc"
TORRC_DIR="/etc/tor/torrc.d"
TORRC_FILE="$TORRC_DIR/birdnet.conf"
HS_DIR="/var/lib/tor/birdnet_hidden_service"
CONFIG_FILE="/etc/birdnet/birdnet.conf"
LOCK_FILE="/run/lock/birdnet-tor.lock"
LOG_DIR="/var/log/birdnet"
LOG_FILE=""
BIRDNET_USER="${BIRDNET_USER:-birdnet}"
BIRDNET_HOME="${BIRDNET_HOME:-/home/$BIRDNET_USER}"
BIRDNET_ROOT="$BIRDNET_HOME/BirdNET-Pi"
BIRDNET_PYTHON="$BIRDNET_ROOT/birdnet/bin/python3"

log_error() {
  echo "[ERROR] $*" >&2
}

log_info() {
  echo "[INFO] $*"
}

require_root() {
  # Package, Tor, and BirdNET configuration changes require root privileges.
  if [ "$EUID" -ne 0 ]; then
    log_error "Run this command with sudo."
    exit 1
  fi
}

setup_logging() {
  # Use a root-owned log directory instead of predictable files in /tmp.
  install -d -m 0750 "$LOG_DIR"
  LOG_FILE=$(mktemp "$LOG_DIR/tor_service_${ACTION}_XXXXXX.log")
  chmod 0600 "$LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
}

acquire_lock() {
  # Prevent overlapping UI requests from racing on Tor's keys and config.
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    log_error "Another Tor configuration operation is already running."
    return 1
  fi
}

cleanup_old_logs() {
  # Keep the most recent three logs for this action.
  mapfile -t old_logs < <(
    find "$LOG_DIR" -maxdepth 1 -type f -name "tor_service_${ACTION}_*.log" \
      -printf '%T@ %p\n' | sort -rn | tail -n +4 | cut -d' ' -f2-
  )
  if [ "${#old_logs[@]}" -gt 0 ]; then
    rm -f -- "${old_logs[@]}"
  fi
}

check_requirements() {
  # Fail with a clear message when this is not a supported Debian/systemd host.
  for command_name in apt-get flock systemctl; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
      log_error "Required command not found: $command_name"
      return 1
    fi
  done
}

install_tor() {
  # Install Tor from the configured Debian repositories when it is absent.
  if command -v tor >/dev/null 2>&1; then
    return 0
  fi

  log_info "Installing Tor..."
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y tor
}

check_tor_user() {
  # Raspberry Pi OS and Debian packages run Tor as debian-tor.
  if ! id "$TOR_USER" >/dev/null 2>&1; then
    log_error "Tor user '$TOR_USER' was not created by the Tor package."
    return 1
  fi
}

ensure_torrc_include() {
  # Debian uses Tor's documented %include syntax for drop-in configuration.
  install -d -m 0755 "$TORRC_DIR"
  if grep -Eq '^[[:space:]]*%include[[:space:]]+/etc/tor/torrc\.d/(\*|\*\.conf)[[:space:]]*$' "$TORRC" 2>/dev/null; then
    return 0
  fi

  log_info "Adding the Tor drop-in include to $TORRC"
  printf '\n%%include /etc/tor/torrc.d/*.conf\n' >> "$TORRC"
}

write_tor_config() {
  # Stage the service config atomically so Tor never reads a partial file.
  local temporary_file
  temporary_file=$(mktemp "$TORRC_DIR/.birdnet.conf.XXXXXX")
  cat > "$temporary_file" <<EOF
# BirdNET-Pi v3 onion service. Managed by update_tor_service.sh.
HiddenServiceDir $HS_DIR
HiddenServiceVersion 3
HiddenServicePort 80 127.0.0.1:80
EOF

  # Tor 0.4.8+ can automatically raise proof-of-work effort during overload.
  if tor --list-torrc-options 2>/dev/null | grep -qx "HiddenServicePoWDefensesEnabled"; then
    echo "HiddenServicePoWDefensesEnabled 1" >> "$temporary_file"
  fi

  chmod 0644 "$temporary_file"
  mv -f "$temporary_file" "$TORRC_FILE"
}

verify_tor_config() {
  # Verify as Tor's service account so key-directory permissions match runtime.
  log_info "Verifying Tor configuration..."
  if ! runuser -u "$TOR_USER" -- tor --verify-config -f "$TORRC"; then
    log_error "Tor rejected the configuration."
    return 1
  fi
}

restart_tor() {
  # Restart only through systemd; never signal unrelated Tor processes.
  log_info "Restarting Tor..."
  if systemctl restart tor@default.service 2>/dev/null; then
    return 0
  fi
  systemctl restart tor.service
}

wait_for_hostname() {
  # Wait for Tor to create and publish the v3 onion identity.
  local hostname=""
  local attempt
  for attempt in $(seq 1 60); do
    if [ -s "$HS_DIR/hostname" ]; then
      hostname=$(tr -d '\r\n' < "$HS_DIR/hostname")
      if [[ "$hostname" =~ ^[a-z2-7]{56}\.onion$ ]]; then
        printf '%s\n' "$hostname"
        return 0
      fi
    fi
    sleep 1
  done

  log_error "A valid v3 onion hostname was not generated within 60 seconds."
  systemctl --no-pager --full status tor@default.service 2>&1 || \
    systemctl --no-pager --full status tor.service 2>&1 || true
  return 1
}

set_config_value() {
  # Rewrite a BirdNET setting while preserving a possible config-file symlink.
  local key="$1"
  local value="$2"
  local temporary_file
  temporary_file=$(mktemp)

  if [ -f "$CONFIG_FILE" ]; then
    grep -v "^${key}=" "$CONFIG_FILE" > "$temporary_file" || true
  fi
  printf '%s=%s\n' "$key" "$value" >> "$temporary_file"
  cat "$temporary_file" > "$CONFIG_FILE"
  rm -f "$temporary_file"
}

send_tor_nostr_notification() {
  # Notify the configured Nostr receiver about the latest onion address without blocking Tor setup on DM failures.
  local event="$1"
  local onion_url="$2"
  local notification_script="$BIRDNET_ROOT/scripts/send_tor_nostr_notification.py"

  if [ ! -x "$BIRDNET_PYTHON" ] || [ ! -f "$notification_script" ]; then
    log_info "Skipping Nostr Tor address DM; BirdNET-Pi Python environment or notification script is missing."
    return 0
  fi

  if runuser -u "$BIRDNET_USER" -- "$BIRDNET_PYTHON" "$notification_script" --event "$event" --onion "$onion_url"; then
    return 0
  fi

  log_error "Nostr Tor address DM failed. Tor configuration was still completed."
  return 0
}

remove_config_value() {
  # Remove a BirdNET setting while preserving a possible config-file symlink.
  local key="$1"
  local temporary_file
  temporary_file=$(mktemp)

  if [ -f "$CONFIG_FILE" ]; then
    grep -v "^${key}=" "$CONFIG_FILE" > "$temporary_file" || true
    cat "$temporary_file" > "$CONFIG_FILE"
  fi
  rm -f "$temporary_file"
}

enable_tor_service() {
  # Configure Tor transactionally and only report enabled after keys exist.
  local event="${1:-enable}"
  local backup_file=""
  local hostname

  install_tor
  check_tor_user
  ensure_torrc_include

  if [ -f "$TORRC_FILE" ]; then
    backup_file=$(mktemp)
    cp -a "$TORRC_FILE" "$backup_file"
  fi

  write_tor_config
  if ! verify_tor_config; then
    if [ -n "$backup_file" ]; then
      cp -a "$backup_file" "$TORRC_FILE"
    else
      rm -f "$TORRC_FILE"
    fi
    rm -f "$backup_file"
    return 1
  fi

  if ! restart_tor || ! hostname=$(wait_for_hostname); then
    log_error "Restoring the previous Tor configuration."
    if [ -n "$backup_file" ]; then
      cp -a "$backup_file" "$TORRC_FILE"
    else
      rm -f "$TORRC_FILE"
    fi
    restart_tor || true
    rm -f "$backup_file"
    return 1
  fi
  rm -f "$backup_file"

  set_config_value "TOR_ENABLED" "1"
  set_config_value "TOR_ONION" "\"http://$hostname\""

  log_info "Tor onion service enabled: http://$hostname"
  send_tor_nostr_notification "$event" "http://$hostname"
}

disable_tor_service() {
  # Disable BirdNET's onion service but retain its keys and stable address.
  local backup_file=""
  if [ -f "$TORRC_FILE" ]; then
    backup_file=$(mktemp)
    cp -a "$TORRC_FILE" "$backup_file"
  fi

  rm -f "$TORRC_FILE"
  if ! verify_tor_config || ! restart_tor; then
    log_error "Restoring the previous Tor configuration."
    if [ -n "$backup_file" ]; then
      cp -a "$backup_file" "$TORRC_FILE"
      restart_tor || true
    fi
    rm -f "$backup_file"
    return 1
  fi
  rm -f "$backup_file"

  set_config_value "TOR_ENABLED" "0"

  log_info "Tor onion service disabled. Its identity was preserved."
}

restart_tor_service() {
  # Restart only an already-configured BirdNET onion service.
  local hostname

  install_tor
  check_tor_user
  if [ ! -f "$TORRC_FILE" ]; then
    log_error "The BirdNET onion service is disabled. Enable it before restarting."
    return 1
  fi

  verify_tor_config
  restart_tor
  hostname=$(wait_for_hostname)
  set_config_value "TOR_ENABLED" "1"
  set_config_value "TOR_ONION" "\"http://$hostname\""

  log_info "Tor onion service restarted: http://$hostname"
  send_tor_nostr_notification "restart" "http://$hostname"
}

reset_tor_service() {
  # Explicitly destroy the old identity, then generate and enable a new one.
  rm -f "$TORRC_FILE"
  verify_tor_config
  restart_tor
  rm -rf -- "$HS_DIR"
  remove_config_value "TOR_ONION"
  enable_tor_service "reset"
}

main() {
  # Validate the request before creating logs or changing the host.
  case "$ACTION" in
    enable|disable|restart|reset) ;;
    *)
      echo "Usage: $0 enable|disable|restart|reset" >&2
      exit 2
      ;;
  esac

  require_root
  setup_logging
  acquire_lock
  cleanup_old_logs
  check_requirements

  case "$ACTION" in
    enable) enable_tor_service ;;
    disable) disable_tor_service ;;
    restart) restart_tor_service ;;
    reset) reset_tor_service ;;
  esac
}

main "$@"
