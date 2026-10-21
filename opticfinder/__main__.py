import argparse
import json

from .engine import plan


def main() -> None:
    parser = argparse.ArgumentParser(description="OpticFinder public-evidence prototype")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Run the loopback-only local web interface")
    serve.add_argument("--port", type=int, default=8765, help="Local port (default: 8765)")
    commands.add_parser("refresh-matrix", help="Refresh the public Meraki accessory-table snapshot")
    check = commands.add_parser("check", help="Print a connection plan as JSON")
    check.add_argument("--endpoint-a", required=True, help="Meraki endpoint A catalog ID")
    check.add_argument("--endpoint-b", required=True, help="Meraki endpoint B catalog ID")
    check.add_argument("--interface-a", required=True, help="Endpoint A interface-group ID")
    check.add_argument("--interface-b", required=True, help="Endpoint B interface-group ID")
    check.add_argument("--speed-gbps", required=True)
    check.add_argument("--distance-m", required=True)
    cable = check.add_mutually_exclusive_group(required=True)
    cable.add_argument("--fiber", help="Legacy fiber grade: OM1-OM5 or OS1/OS2")
    cable.add_argument("--cable-type", help="OM1-OM5, OS1/OS2, CAT5E, CAT6, CAT6A, DAC")
    args = parser.parse_args()
    if args.command == "serve":
        if not 1 <= args.port <= 65535:
            parser.error("--port must be between 1 and 65535")
        from .server import serve_local
        serve_local(args.port)
    elif args.command == "refresh-matrix":
        from .matrix import refresh_matrix
        matrix = refresh_matrix()
        print(f"Imported {len(matrix['accessories'])} Meraki accessories "
              f"on {matrix['retrieved_on']}. This is not the Cisco TMG matrix.")
    else:
        try:
            result = plan({
                "endpoint_a": args.endpoint_a,
                "endpoint_b": args.endpoint_b,
                "interface_a": args.interface_a,
                "interface_b": args.interface_b,
                "speed_gbps": args.speed_gbps, "distance_m": args.distance_m,
                **({"fiber": args.fiber} if args.fiber is not None else {"cable_type": args.cable_type}),
            })
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
