from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Any

from zellij_presence.collectors import CLICollector, PluginStateCollector
from zellij_presence.collectors.base import Collector
from zellij_presence.config import PresenceConfig, init_config, load_config
from zellij_presence.normalizer import PresenceNormalizer
from zellij_presence.publishers import DiscordRPCPublisher, HTTPPresencePublisher, JSONFilePublisher
from zellij_presence.sanitizer import PresenceSanitizer
from zellij_presence.service import PresenceService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zellij-presence")
    parser.add_argument("--config", help="Path to config TOML.")
    parser.add_argument("--safe-mode", action="store_true", help="Force privacy-safe mode.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the presence pipeline.")
    run_parser.add_argument("--dry-run", action="store_true", help="Print presence only.")
    run_parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Polling interval in seconds (must be >= 0.1).",
    )

    subparsers.add_parser("status", help="Print current JSON presence snapshot.")

    config_parser = subparsers.add_parser("config", help="Configuration commands.")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    init_parser = config_subparsers.add_parser("init", help="Create default config file.")
    init_parser.add_argument("--path", help="Target config path.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing file.")

    return parser


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def apply_cli_overrides(config: PresenceConfig, args: argparse.Namespace) -> PresenceConfig:
    if args.safe_mode:
        config.safe_mode = True
    if getattr(args, "poll_interval", None) is not None:
        config.poll_interval_seconds = max(0.1, float(args.poll_interval))
    return config


def command_config_init(args: argparse.Namespace) -> int:
    try:
        path = init_config(args.path, force=args.force)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(path)
    return 0


def _build_service(
    config: PresenceConfig,
    dry_run: bool,
    logger: logging.Logger,
) -> tuple[PresenceService, list[Any]]:
    publishers = []
    closeables: list[Any] = []
    collector = _build_collector(config, logger)

    if not dry_run:
        publishers.append(JSONFilePublisher(config.publish.file_path))

    if config.publish.http_enabled:
        http_publisher: HTTPPresencePublisher = HTTPPresencePublisher(
            host=config.publish.http_host,
            port=config.publish.http_port,
        )
        publishers.append(http_publisher)
        closeables.append(http_publisher)

    if config.publish.discord_enabled and config.publish.discord_client_id:
        discord_publisher = DiscordRPCPublisher(
            client_id=config.publish.discord_client_id,
            socket_path=config.publish.discord_socket_path or None,
            logger=logger,
        )
        publishers.append(discord_publisher)
        closeables.append(discord_publisher)

    service = PresenceService(
        collector=collector,
        normalizer=PresenceNormalizer(),
        sanitizer=PresenceSanitizer(config),
        publishers=publishers,
        dry_run=dry_run,
        idle_timeout_seconds=config.idle_timeout_seconds,
        logger=logger,
    )
    return service, closeables


def _build_collector(config: PresenceConfig, logger: logging.Logger) -> Collector:
    strategy = config.collector.strategy
    cli_collector = CLICollector()
    if strategy == "cli":
        return cli_collector
    if strategy == "plugin":
        return PluginStateCollector(
            state_file=config.collector.plugin_state_file,
            max_age_seconds=config.collector.plugin_max_age_seconds,
            fallback_collector=None,
            logger=logger,
        )
    return PluginStateCollector(
        state_file=config.collector.plugin_state_file,
        max_age_seconds=config.collector.plugin_max_age_seconds,
        fallback_collector=cli_collector,
        logger=logger,
    )


def _close_closeables(closeables: list[Any]) -> None:
    for item in closeables:
        close_fn = getattr(item, "close", None)
        if callable(close_fn):
            close_fn()


def command_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config = apply_cli_overrides(config, args)
    logger = logging.getLogger("zellij_presence")
    service, closeables = _build_service(config, args.dry_run, logger)

    def _stop_handler(_sig: int, _frame: object) -> None:
        service.stop()

    signal.signal(signal.SIGINT, _stop_handler)
    signal.signal(signal.SIGTERM, _stop_handler)
    try:
        service.run_forever(config.poll_interval_seconds)
    finally:
        _close_closeables(closeables)
    return 0


def command_status(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config = apply_cli_overrides(config, args)
    snapshot_path = Path(config.publish.file_path).expanduser()

    if snapshot_path.exists():
        content = snapshot_path.read_text(encoding="utf-8").strip()
        if content:
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                print(content)
            else:
                print(json.dumps(parsed, indent=2, sort_keys=True))
            return 0

    logger = logging.getLogger("zellij_presence")
    service, closeables = _build_service(config, dry_run=True, logger=logger)
    try:
        snapshot = service.collect_once()
    finally:
        _close_closeables(closeables)
    print(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True))
    return 0


def _normalize_global_flag_order(argv: list[str]) -> list[str]:
    """
    Allow global flags both before and after subcommands.

    argparse treats options declared on the root parser as valid only before the
    subcommand token. This preprocessor moves known global flags to the front so
    `zellij-presence run --verbose` works the same as
    `zellij-presence --verbose run`.
    """

    global_standalone = {"--verbose", "--safe-mode"}
    result_front: list[str] = []
    result_rest: list[str] = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token in global_standalone:
            result_front.append(token)
            i += 1
            continue
        if token == "--config":
            result_front.append(token)
            if i + 1 < len(argv):
                result_front.append(argv[i + 1])
                i += 2
            else:
                i += 1
            continue
        if token.startswith("--config="):
            result_front.append(token)
            i += 1
            continue
        result_rest.append(token)
        i += 1
    return [*result_front, *result_rest]


def main(argv: list[str] | None = None) -> int:
    argv = _normalize_global_flag_order(argv if argv is not None else sys.argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    if args.command == "run":
        return command_run(args)
    if args.command == "status":
        return command_status(args)
    if args.command == "config" and args.config_command == "init":
        return command_config_init(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
