"""Command line of the data pipeline.

Usage:
    python -m mix_sandbox fetch [--only pse|era5] [--offline]
    python -m mix_sandbox build
    python -m mix_sandbox validate [--calibrate]
    python -m mix_sandbox card
    python -m mix_sandbox simulate [--scenario today] [--weather-year 2025] [--set pv=40 storage_gwh=60]
"""

from __future__ import annotations

import argparse
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mix_sandbox", description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="download PSE reports and ERA5 series (cached)")
    p_fetch.add_argument("--only", choices=["pse", "era5"])
    p_fetch.add_argument("--offline", action="store_true", help="use cached downloads only")

    sub.add_parser("build", help="write profiles and assumptions to docs/data/")
    p_val = sub.add_parser("validate", help="run the 2025 validation and write results/validation_2025.*")
    p_val.add_argument("--calibrate", action="store_true", help="grid search of the exchange parameters")

    sub.add_parser("card", help="write the social preview image docs/card.png (needs matplotlib)")

    p_sim = sub.add_parser("simulate", help="run one scenario and print the yearly balance")
    p_sim.add_argument("--scenario", default="today")
    p_sim.add_argument("--weather-year", default=None, help="weather year (default: the reference year)")
    p_sim.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE", help="override scenario parameters")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "fetch":
        from . import fetch
        fetch.run(args.only, args.offline)
    elif args.command == "build":
        from . import build
        build.run()
    elif args.command == "validate":
        from . import validate
        validate.run(args.calibrate)
    elif args.command == "card":
        from . import card
        card.run()
    elif args.command == "simulate":
        from . import simulate
        overrides = dict(item.split("=", 1) for item in args.set)
        simulate.run(args.scenario, args.weather_year, overrides)
    return 0


if __name__ == "__main__":
    sys.exit(main())
