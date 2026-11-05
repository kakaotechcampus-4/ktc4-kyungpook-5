"""Run the same meeting judge set against two model env files.

No API keys are printed. The caller supplies separate env files so Luna and
Terra can point at their own MLAPI deployments.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


def run_one(env_file: Path, output: Path, *, holdout: bool) -> dict:
    command = [
        sys.executable,
        "-m",
        "app.ai.scripts.check_meeting_judge",
        "--eval-set",
        "--env-file",
        str(env_file),
        "--json",
        str(output),
    ]
    if holdout:
        command.append("--holdout")
    subprocess.run(command, check=True)
    return json.loads(output.read_text(encoding="utf-8"))


def run_rag(env_file: Path, judge_report: dict, output: Path, *, holdout: bool) -> dict:
    load_dotenv(env_file.resolve(), override=True)
    queries_path = output.with_suffix(".queries.json")
    queries_path.write_text(
        json.dumps(
            {"queries": {row["id"]: row.get("query", "") if row.get("pred") else "" for row in judge_report["records"]}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "app.ai.scripts.eval_retrieval",
        "--search",
        "records",
        "--no-rewrite",
        "--queries",
        str(queries_path),
        "--json",
        str(output),
    ]
    if holdout:
        command.append("--holdout")
    subprocess.run(command, check=True)
    return json.loads(output.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--luna-env", type=Path, required=True)
    parser.add_argument("--terra-env", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--holdout", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    luna = run_one(args.luna_env, args.output_dir / "luna.json", holdout=args.holdout)
    terra = run_one(args.terra_env, args.output_dir / "terra.json", holdout=args.holdout)
    luna_rag = run_rag(args.luna_env, luna, args.output_dir / "luna-rag.json", holdout=args.holdout)
    terra_rag = run_rag(args.terra_env, terra, args.output_dir / "terra-rag.json", holdout=args.holdout)
    comparison = {
        "luna": luna["summary"],
        "terra": terra["summary"],
        "luna_rag": luna_rag["summary"],
        "terra_rag": terra_rag["summary"],
        "delta_terra_minus_luna": {
            key: terra["summary"].get(key) - luna["summary"].get(key)
            for key in ("balanced_accuracy", "p50_s", "p95_s", "krw_per_1000")
            if isinstance(terra["summary"].get(key), (int, float))
            and isinstance(luna["summary"].get(key), (int, float))
        },
    }
    (args.output_dir / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
