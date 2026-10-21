# OpticFinder

Find cable and transceiver options for connections between **Cisco Meraki MX
and MS devices**. Choose a device and port group at each end, then select the
speed, cable type, and length. OpticFinder shows matching parts and connection
limits using bundled public documentation data.

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

The development server is local-only. Do not expose it directly to the internet.
For a Raspberry Pi hosted behind HTTPS, see [the deployment guide](deploy/README.md).

## How to use it

1. Choose Device A and Device B, including a port group for each.
2. Choose a compatible speed, cable family, specific type or grade, and total length.
3. Click **Check connection** to see the options and required parts.

Choices with only one available option are selected automatically. The same
model can be selected twice to represent two separate devices.
Sources and installation checks are available in the collapsed result details.

## Data and limitations

Device ports and supported accessories are based on public Cisco/Meraki
documentation. Planning uses a bundled snapshot, **not the complete Cisco optics
matrix** or a live compatibility service. It does not validate an installed link
or calculate its optical loss budget.

The reference page gives general cabling guidance; its tables do not add support
to the planner. For example, Cat7/Cat8 appear in the reference but are not planner
cable choices. No match means no option in the bundled data, not proof that a
connection is impossible.

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
A command-line planner is also available:

```powershell
.\.venv\Scripts\python.exe -m opticfinder check --help
```

Keep credentials, customer data, and vendor-internal documents out of the repository.
