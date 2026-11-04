"""#239: 저장한 실패 초안을 API/설정 없이 재검사하고 새 결과 파일을 쓴다."""

import argparse
import hashlib
import json
from pathlib import Path

from app.ai.scripts.planning_validation_diagnostics import ValidationSnapshot, replay_snapshot


def replay_file(input_path: Path, output_path: Path) -> dict:
    raw = input_path.read_bytes()
    snapshot = ValidationSnapshot.model_validate_json(raw)
    report = replay_snapshot(snapshot)
    report['source_snapshot_sha256'] = hashlib.sha256(raw).hexdigest()
    with output_path.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = replay_file(args.input, args.output)
        print(json.dumps({k: result[k] for k in ('status', 'reproduced', 'same_validator_source')}, ensure_ascii=False))
        return 0 if result['reproduced'] else 1
    except Exception as error:
        print(f'재검사 오류: {type(error).__name__}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
