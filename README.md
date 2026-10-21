# OpticFinder

A local-first, Meraki-focused prototype for public-evidence connection planning.
Developed on Windows; the standard-library Python application is portable to
Raspberry Pi OS. Python 3.11 or newer is required. No external packages are needed.

## Run on Windows

From the repository directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m opticfinder serve
```

Open **http://127.0.0.1:8765**. Stop with Ctrl+C in the terminal running the server.
The server binds only to loopback; it is not accessible from other computers.
If the port is occupied, use `-m opticfinder serve --port 8766`.
Interpreter paths are explicit; activation is not required.

Command-line example:

```powershell
.\.venv\Scripts\python.exe -m opticfinder check --endpoint-a ms130-24x --endpoint-b ms130-24x --interface-a sfp-uplink --interface-b sfp-uplink --speed-gbps 10 --distance-m 30 --cable-type OM3
```

Both interface-group flags are required. For native copper, use
`--interface-a rj45-1g --interface-b rj45-1g`, `--speed-gbps 1`, and
`--cable-type CAT6`. The same model selected twice represents two separate
physical devices. Only Meraki models are included.
In the web form, speed, cable type, and length appear after you select a
catalog-compatible device and port-group combination. Available speeds and
cable types are limited to profiles supported by that selection.
Dropdowns with exactly one available choice select it automatically without a
placeholder; dependent dropdowns update immediately.
Cable selection uses a family first (Multimode, Single Mode, Copper Ethernet,
or DAC), then a compatible type/grade. The API still receives the specific
`cable_type`; the family selector is only a UI filter.
Results show a catalog-match heading, side-by-side device/optic cards, a parts
summary, and cable length/reach. Installation-specific requirements remain visible
on the relevant option; other checks, source provenance, and raw JSON are collapsed
under Technical details and sources. The API's `not_verified` state is retained
for consumers but is not used as a user-facing heading.
The dashboard uses an original magnifying-glass mark and blue-and-white styling,
not an official Cisco logo. Its header/footer identify it as an independent,
non-endorsed prototype. All styling and assets remain local.
The header and footer link to `/limitations`, a standalone copper/fiber quick reference
covering speed-by-cable channel lengths for Cat5e/Cat6/Cat6A/Cat7/Cat8, multimode
OM1-OM5, and single-mode OS1/OS2 application examples. It is independent of the
device catalog and contains no optic part lists. Fiber distances are tied to
named Ethernet standards, not presented as universal cable-grade limits.
Installation notes and public cabling references are included. It is available offline.
The reference page shows all fiber tables as static sections without dropdowns
or JavaScript; the planner retains its two-step family and grade selection.

Run tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
`tests/test_connection_scenarios.py` contains named, table-driven examples for
fiber standards, native copper, SFP copper modules, mixed endpoint connections,
and incompatible selections. Add a scenario there when adding or changing a
supported connection profile.
For dashboard result-rendering checks (requires Node.js, no packages):

```powershell
node --test tests\test_dashboard.cjs
```

## Demo scope and limitations

The catalog models **37 current MX/MS devices**, reviewed **October 20, 2026**:
all eleven MS130 variants, MS130R-8P, all twelve MS150 variants, MS450-12,
MX67/MX67W/MX67C, MX68/MX68W/MX68CW, MX75, MX85, MX95, MX105, MX250 and MX450.
Current means not past the published **end-of-sale** date on that review date,
not merely still supported. MS450-12 (October 29, 2026) and MX67C/MX68CW
(November 27, 2026) have announced end-of-sale dates and remain included with
selection notices. This is a dated inventory, not an automatic lifecycle feed.
Older MS120/125/210/225/250/350/355/390/410/425 models are excluded.
Cloud-managed Catalyst, C8000, Z-series and virtual appliances are outside this
MX/MS-named hardware scope.

Interface selectors describe documented **port groups**, not physical port numbers.
Their labels show port count and rated speed, matching the installation guide:
MS130-24P offers `24 x 1G RJ45 ports` and `4 x 1G SFP ports`; MS130-24X offers
`18 x 1G RJ45 ports`, `6 x 2.5G RJ45 ports`, and `4 x 10G SFP+ ports`.
Supported lower link speeds remain separate from these simple hardware labels:
the 2.5G RJ45 group can operate at 1G, and the 10G SFP+ group supports 1G optics.
The planner still only offers speeds covered by its connection profiles.
Native RJ45 and pluggable copper modules are handled separately.
MS150 multigigabit groups support 1/2.5/5G; MS130-X and MX95/105 WAN copper
groups support 1/2.5G. Copper planning covers 1G and 2.5G to 100m on certified
Cat5e/Cat6/Cat6A, and 5G to 100m on certified Cat5e/Cat6/Cat6A.
MS450 exposes twelve 40G QSFP+ and two 100G QSFP28 data ports.
MX WAN and LAN groups are separate; MX67's convertible port is counted once.
Paired WAN activation constraints on MX75/85/95/105 are shown with selections
and results. The planner evaluates one physical link, not concurrent WAN
capacity, routing, firewall throughput, PoE delivery or logical network design.
Only documented rated modes are offered on MX250/450 SFP+ and MS450 QSFP ports;
unverified downshift/breakout modes are not inferred.
Dedicated management ports and stacking are not modeled.

| Demo | Result |
| --- | --- |
| Two MS130-24X, SFP+ uplinks, 10G, OM3, 30m | MA-SFP-10GB-SR at each end; 300m catalog limit |
| Two MS130-24X, SFP+ uplinks, 10G, OS2, 1km | LR (10km) and ER (40km) alternatives; shorter reach listed first |
| Two MS130-24X, SFP+ uplinks, 10G, OS2, 20km | MA-SFP-10GB-ER at each end; check optical power/attenuation |
| Two MS130-24X, SFP+ uplinks, 10G, DAC, 2m | One MA-CBL-TA-3M assembly; no separate optics |
| MS130-24X to MS130-24P, SFP uplinks, 1G, OM3 | MA-SFP-1GB-SX at each end; 550m catalog limit |
| Two native RJ45 ports, 1G, Cat5e/Cat6/Cat6A, up to 100m | No transceiver required |
| Native RJ45 to SFP uplink, 1G copper, up to 100m | MA-SFP-1GB-TX only at the SFP end |
| 10G on MS130-24P or fiber on native RJ45 | No catalog match |
| MX95 SFP+ LAN to MS150-24P-4X uplink, 10G, OM3, 100m | MA-SFP-10GB-SR at each end |
| MX95 2.5G RJ45 WAN to MS130-24X multigigabit, Cat6, 100m | Native 2.5G; check MX paired WAN activation |
| Two MS150-24MP-4X multigigabit groups, 5G, Cat6A, 100m | Native 5G, no transceivers |
| MS130R SFP to MS130-24P SFP, 1G, OM3, 100m | GLC-SX-MM-RGD at rugged end; MA-SFP-1GB-SX at other end |
| Two MS450-12 100G groups, OM4, 100m | MA-QSFP-100G-SR4 at each end, MPO12 cabling |

Meraki part numbers, model-family compatibility and reach were read from the
public accessories page's HTML tables (the simplified text view omits these tables).
The native copper cable-category rules are labeled `engineering_rule`, distinct
from vendor-qualified accessory records. Copper length includes all patch leads;
the channel must be certified. An actual OM/OS fiber grade is required rather than
a generic MMF/SMF choice. Fiber must meet the transceiver's requirements.

All options remain provisional: firmware restrictions, individual ports,
connector polish, optical loss budget, cabling and actual link operation must be
checked before purchasing or deploying. `catalog_endpoint_match: documented`
means a curated model/port-family match, not verified installed-link support.
There are no 10G copper profiles; choosing Cat6A does not override
the selected port's capabilities. No match in this limited catalog is not proof
that a compatible solution does not exist.

Do not purchase parts using this prototype's output.
There is no 25G, AOC, breakout, FEC, optical power-budget or inventory engine yet.
Long-reach optics are alternatives, not automatic upgrades: short links can need
attenuation to avoid receiver overload. Reach alone is not an optical power budget.

## Matrix data and coverage

`opticfinder/meraki_matrix.json` is a factual snapshot of all **14 Meraki-branded
transceiver part numbers and two data-port DAC assemblies** in the reviewed
[public Meraki accessory tables](https://documentation.meraki.com/Platform_Management/Product_Information/Overviews_and_Datasheets/Small-Form_Factor_Pluggable_(SFP)_and_Stacking_Accessories).
It retains the listed MS, MX and cloud-managed Catalyst family qualifications,
fiber-specific reaches, and qualifications requiring separate handling.
Stacking/StackPower cables and uplink modules are deliberately excluded.

This is **not the complete Cisco TMG matrix**, nor complete link planning for
every Meraki model. Cisco's [matrix manual](https://www.cisco.com/c/en/us/td/docs/interfaces_modules/transceiver_modules/compatibility/matrix/TMG_CM_Tool_User_Manual.html)
documents exporting search results, not a guaranteed complete public bulk feed.
Additional Cisco-branded optics and software-specific qualifications are not
bulk-imported. Four explicitly documented rugged GLC modules for MS130R are
curated separately in `catalog.json`, with Cisco reach/connector specifications.
Mixed rugged/Meraki links use compatible optical standards and the smaller
reach at the two ends; rugged optical modules have a 2m minimum. ZX requires
loss-budget/attenuation checks. Ordinary MA optics are not offered on MS130R.
The bundled accessory data covers more families than the 37 selectable models.
Adding another exact model requires documented interfaces and `matrix_families`
in `catalog.json`. A family optic listing does not establish physical port
availability, firmware support, or stacking/data-port interchangeability.

The engine generates `connection_profiles` from this snapshot, rather than a
separate manually maintained list. This includes documented MS130-X ER and DAC
options and OM1/OM2/OS1 media. LX10 with a mode-conditioning cable remains recorded
but is not offered for ordinary MMF. LRM/C9300X and copper-module exceptions
are retained; family-specific media qualifications are not combined.
Native copper profiles are independent of copper SFP eligibility. Profiles with
`parts_by_endpoint` use that mapping (endpoint ID to port-kind/part map) instead
of the generic `parts_by_port_kind`. Mixed rugged optical profiles also require
one endpoint from each `endpoint_groups` set; this prevents duplicate or
incorrect same-family options. Both dashboard filtering and API planning apply
these rules.

To refresh from the public source explicitly:

```powershell
.\.venv\Scripts\python.exe -m opticfinder refresh-matrix
```

Review the generated snapshot and rerun tests before deploying it. Refresh
requires internet, validates parsing before replacing the file, and fails if a
previously imported accessory disappears. It does not promote a source's review
state or establish perpetual completeness. Normal planning stays offline.
`GET /api/matrix` exposes the imported facts; `GET /api/catalog` includes
`matrix_coverage` and the generated profiles used by both the form and engine.

## Public-data policy

`opticfinder/catalog.json` contains manually curated device records and links to
public vendor documentation; `meraki_matrix.json` contains extracted accessory
facts, not a mirror of the vendor document. No vendor-internal tools, customer data, credentials,
document mirrors, or authenticated vendor portals are required.
Runtime checks use the bundled catalog offline; opening a source link requires internet.
Public access does not grant redistribution rights. Review applicable terms before
expanding ingestion; do not bypass access controls or reproduce vendor documents.

Each source records a review state, review date (null if unreviewed), and claim
scope. A review date is not a guarantee that the source has not changed.
Dataset changes should be checked against the original public source and covered
by tests before support states are promoted.

## Output contract

`POST /api/plan` requires `endpoint_a`, `endpoint_b`, `interface_a`,
`interface_b`, `speed_gbps`, `distance_m`, and `cable_type`. Interface-group IDs
must belong to the selected endpoint; empty or omitted groups are invalid.
Model IDs, interface groups and cable choices come from `GET /api/catalog`
(schema version 6). Numbers must be positive and finite. Cable choices are OM1-OM5,
OS1/OS2, CAT5E, CAT6, CAT6A, and DAC (case-insensitive). Not every grade has a
matching profile for every device.

Legacy `fiber` remains accepted instead of `cable_type` for fiber only.
Results contain `status` (`not_verified` or `no_catalog_match`), normalized `request`,
separate `endpoint_support` and `link_interoperability` states, `candidates`,
`message`, `next_steps`, and public `sources`.
Candidate fields include the standard, `endpoint_optic_candidates` keyed by
endpoint, cable, wavelength, `documented_profile_reach_m`, and source IDs.
Meraki candidates also include `endpoint_connection_options`, identifying the
selected interface group, connection type (`native_rj45`, `transceiver`, or
`direct_attach`) and part number (null for native copper or integrated DAC ends).
DAC candidates specify `assembly_part` and `assembly_length_m`: one cable assembly,
not two separately purchased modules. Input length is the minimum required route;
a longer fixed-length assembly may be offered. `exclusions` explains applicable
reach/port rejections.
Reach is a catalog specification, not a validated loss budget.
Sources and next steps are scoped to the selected endpoint vendors.
Invalid API input returns HTTP 400 with `error`; invalid CLI input exits nonzero.
No catalog match is a normal planning result, not a transport failure.

## Credentials and deployment

No token is needed or used in this version. Do not paste tokens into chat, source,
test fixtures, or commits. The previously disclosed Webex token must be regenerated
before any future use. `.env` files and virtual environments are ignored by Git.
No Webex adapter, webhook, tunnel, or external AI calls are implemented yet.

This is a **development server**, not a production deployment. Do not expose it
with a tunnel or router port forwarding. Before enabling Webex or moving to a Pi,
implement signed webhook validation, durable delivery handling, appropriate
rate limits, and operational logging without message content or credentials.
Then use a production HTTP service with controlled HTTPS ingress and startup
supervision. Recreate the virtual environment on the Pi; do not copy the Windows
environment. Promotion also requires vendor-reviewed endpoint records and real
link validation. Hosting on a Pi alone does not make the application production-ready.
