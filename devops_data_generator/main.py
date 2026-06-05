#!/usr/bin/env python3

import argparse
import json
import logging
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from orchestrator import DevOpsDataOrchestrator


def setup_logging(log_config: dict):
    log_file = log_config.get("file", "logs/gitlab_data_generator.log")
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    logging.basicConfig(
        level=getattr(logging, log_config.get("level", "INFO")),
        format=log_config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def main():
    parser = argparse.ArgumentParser(description="GitLab DevOps data generator")
    parser.add_argument("--mode", choices=["single", "continuous"], default="single")
    parser.add_argument("--interval", type=int)
    parser.add_argument("--config", type=str)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    config_dir = args.config or os.path.join(project_root, "config")
    orchestrator = DevOpsDataOrchestrator(config_dir)
    setup_logging(orchestrator.config_loader.get_logging_config())

    if args.status:
        print(json.dumps(orchestrator.get_status(), indent=2, ensure_ascii=False))
        return
    if args.mode == "single":
        raise SystemExit(0 if orchestrator.run_single_cycle() else 1)
    orchestrator.run_continuous(args.interval)


if __name__ == "__main__":
    main()
