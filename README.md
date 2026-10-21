# OpticFinder

Find cable and transceiver options for connections between **Cisco Meraki MX
and MS devices**. Choose two devices to see all catalog-supported connection
options, usable port groups, required parts, and cable limits. Optional detailed
mode filters by port group, speed, cable type, and length.

**Alpha prototype:** Results may be inaccurate or incomplete. Verify device
support, firmware requirements, and installed cabling before purchasing or deploying.
This is an independent project, not an official Cisco tool or endorsed by Cisco.

## What it does

- Plans fiber, native copper Ethernet, and supported direct-attach cable connections.
- Shows compatible choices, parts needed at each end, and maximum cable length.
- Includes a separate **Copper and Fiber limits** reference with easy-to-read cable tables.
- Runs locally without credentials, external services, or an internet connection.

The catalog includes **37 MX/MS models**, reviewed October 20, 2026, across
MS130, MS130R, MS150, MS450, and MX67 through MX450 families. Model availability
is a dated snapshot, not a live product inventory. Management and stacking ports
are excluded.

## Run locally

Requires **Python 3.11 or newer**. No external Python packages are needed.
From the project folder in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m opticfinder serve
```

Open **http://127.0.0.1:8765**. Stop the server with **Ctrl+C**.
If the port is occupied, add `--port 8766` to the serve command.
Restart after Python code changes; refresh the browser after UI changes.

For laptop or LAN testing without ngrok, bind to your laptop's specific IPv4
address (find it with `ipconfig`):

```powershell
.\.venv\Scripts\python.exe -m opticfinder serve --host 192.168.1.25 --port 8765
```

Replace `192.168.1.25` with your own address and open **http://192.168.1.25:8765**.
The printed IP and port must be used exactly. Loopback remains the default;
wildcard binds (`0.0.0.0`) are not supported. LAN access may require an
organization-approved Windows Firewall rule on a trusted private network.
No ngrok account or internet connection is needed.

The development server is for trusted local networks only and has no
authentication or TLS. Do not expose it directly to the internet.
For Raspberry Pi hosting through an ngrok HTTPS tunnel, see
[the deployment guide](deploy/README.md). Direct hosting is documented as an alternative.

## How to use it

1. Choose Device A and Device B.
2. Click **Show all options**. No port group, speed, or cable input is required.
3. Each result lists alternative usable ports at each end, parts, cable grades
   and maximum lengths (or a fixed-length DAC assembly). Choose one port option
   at each end, not every listed alternative. Check any minimum cable length.

Equivalent connections are combined into one result rather than counted once
per cable grade. For example, a single Copper Ethernet option lists Cat5e, Cat6,
Cat6A, Cat7 and Cat8 together. Speeds, required parts and installation requirements that
differ remain separate; fiber grades retain their individual reach limits.
Equivalent DAC connections also share one result, listing the available
fixed-length assemblies and their part numbers. Choose one assembly long enough
for the route; the listed lengths are discrete choices, not a continuous range.

To narrow the results, switch to **Detailed**, choose port groups at each end,
then select speed, cable family, grade and total length. Click **Check connection**.
Port groups describe alternatives, not individual physical port numbers.

Choices with only one available option are selected automatically. The same
model can be selected twice to represent two separate devices.
Sources and installation checks are available in the collapsed result details.

## Data and limitations

Device ports and supported accessories are based on public Cisco/Meraki
documentation. Planning uses a bundled snapshot, **not the complete Cisco optics
matrix** or a live compatibility service. It does not validate an installed link
or calculate its optical loss budget.

The reference page gives general cabling guidance; its tables do not add device
speeds or accessory qualifications to the planner. Copper choices include Cat7
and RJ45-compatible TIA Cat8 / ISO Cat8.1 for the modeled 1G/2.5G/5G applications,
up to 100 m including patch leads, provided the complete channel meets the
selected application's requirements. Cat7 labeling alone does not establish
Class F performance. Cat8.2 connectors are not supported. Check shield continuity
and termination for both categories. These choices do not add 10G/25G/40G copper
support to devices or optics. No match means no option in the bundled data, not
proof that a connection is impossible.

To refresh the public Meraki accessory snapshot (requires internet):

```powershell
.\.venv\Scripts\python.exe -m opticfinder refresh-matrix
```

Review changes before using them. This command does not update device port
layouts, lifecycle dates, or the reference page.

## Development

The application uses Python's standard library with a plain HTML/CSS/JavaScript
dashboard. Device records live in `opticfinder/catalog.json`; imported accessory
data lives in `opticfinder/meraki_matrix.json`.

Run the Python tests and dashboard checks (Node.js required for the latter):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests\test_dashboard.cjs
```

A JSON API is available at `/api/catalog`, `/api/matrix`, and `/api/plan`.
Post `{"mode":"devices","endpoint_a":"ms130-24x","endpoint_b":"ms130-24p"}`
to `/api/plan` for device-only browsing. Candidates group usable port alternatives
by equivalent connection (combining cable grades) and include `speed_gbps`, `cable_options` (grade to maximum
reach in meters), and `minimum_distance_m`. No route length is assumed or checked.
Device-only DAC candidates include `assembly_options` (`part` and `length_m`)
instead of a single assembly part/length; their `cable_options.DAC` is the longest
listed assembly, not an arbitrary supported cable length.
Detailed API requests retain their required port, speed, length and cable fields.
A command-line planner is also available:

```powershell
.\.venv\Scripts\python.exe -m opticfinder check --help
.\.venv\Scripts\python.exe -m opticfinder check --devices-only --endpoint-a ms130-24x --endpoint-b ms130-24p
```

Keep credentials, customer data, and vendor-internal documents out of the repository.
