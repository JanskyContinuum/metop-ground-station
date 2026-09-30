# Existing station network (preserved)

This topology was already configured in the supplied engineering report,
sections 5 and 6. The application does not configure this network.

```text
Internet / building LAN
        |
  Ethernet + PoE
        |
  Pi 5 "antena" ----- local USB ----- SDRplay RSP1B
        |
  wlan0: existing NetworkManager Wi-Fi AP
  ipv4.method shared; historical address 10.42.0.1
        |
  Pi Zero "rotor": Wi-Fi client
        |
  existing rotctld, TCP 4533
        |
       UART
        |
       MD-02 -> SPX-02
```

The laptop accesses the Pi 5 Ethernet/LAN address using HTTP. It does not execute
SSH recording commands. The Pi 5 reaches the rotor over the already configured
dedicated wireless network. The report describes the existing rotctld service on
the Pi Zero; this application neither installs nor modifies it.

Historical addresses conflict: the report names `10.142.0.147`, while later code
uses `10.42.0.147`, and early tests used a different private subnet. The first is
inconsistent with the reported `10.42.0.1` AP network. None is assumed to be the
current client address. Configure `rotor.host` only after verification.

## Non-destructive verification on the real Pi

```bash
hostname -I
ip addr
ip neigh
nmcli connection show
nmcli device
ping -c 3 <rotor-host>
nc -vz <rotor-host> 4533
```

On the Pi Zero, if the existing service name is known:

```bash
systemctl status <existing-rotctld-service>
```

Confirm Pi 5 Ethernet reachability from the laptop, wlan0/AP address, Pi Zero's
actual address and TCP port, then use the application's read-only rotor test.
Do not infer the UART path or Hamlib device/model parameters from obsolete USB
test scripts. Verify the existing setup with the station owner. No MD-02 COM1,
NetworkManager, boot or systemd settings are modified here.

The historical report contains a Wi-Fi PSK. It stays outside this public
repository. If documenting credentials locally, use `<WIFI_PASSWORD>` in any
shareable example. Avoid diagnostic commands that print saved secrets.
