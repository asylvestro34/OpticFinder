import argparse
import json

from .engine import plan


def main() -> None:
    parser = argparse.ArgumentParser(description="OpticFinder public-evidence prototype")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Run the local development web interface")
    serve.add_argument("--port", type=int, default=8765, help="Local port (default: 8765)")
    serve.add_argument("--host", default="127.0.0.1",
                       help="Specific local IPv4 address to bind (default: 127.0.0.1)")
    commands.add_parser("refresh-matrix", help="Refresh the public Meraki accessory-table snapshot")
    check = commands.add_parser("check", help="Print a connection plan as JSON")
    check.add_argument("--endpoint-a", required=True, help="Meraki endpoint A catalog ID")
    check.add_argument("--endpoint-b", required=True, help="Meraki endpoint B catalog ID")
    check.add_argument("--devices-only", action="store_true", help="List all catalog options for the two devices")
    check.add_argument("--interface-a", help="Endpoint A interface-group ID")
    check.add_argument("--interface-b", help="Endpoint B interface-group ID")
    check.add_argument("--speed-gbps")
    check.add_argument("--distance-m")
    cable = check.add_mutually_exclusive_group()
    cable.add_argument("--fiber", help="Legacy fiber grade: OM1-OM5 or OS1/OS2")
    cable.add_argument("--cable-type", help="OM1-OM5, OS1/OS2, CAT5E, CAT6, CAT6A, CAT7, CAT8, DAC")
    args = parser.parse_args()
    if args.command == "serve":
        if not 1 <= args.port <= 65535:
            parser.error("--port must be between 1 and 65535")
        from .server import serve_local
        try:
            serve_local(args.port, args.host)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
    elif args.command == "refresh-matrix":
        from .matrix import refresh_matrix
        matrix = refresh_matrix()
        print(f"Imported {len(matrix['accessories'])} Meraki accessories "
              f"on {matrix['retrieved_on']}. This is not the Cisco TMG matrix.")
    else:
        try:
            endpoints = {
                "endpoint_a": args.endpoint_a,
                "endpoint_b": args.endpoint_b,
            }
            detailed = {
                "interface_a": args.interface_a,
                "interface_b": args.interface_b,
                "speed_gbps": args.speed_gbps, "distance_m": args.distance_m,
                **({"fiber": args.fiber} if args.fiber is not None else {"cable_type": args.cable_type}),
            }
            if args.devices_only and any(value is not None for value in detailed.values()):
                parser.error("--devices-only cannot be combined with port, speed, distance or cable filters")
            result = plan({**endpoints, **({"mode": "devices"} if args.devices_only else detailed)})
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
