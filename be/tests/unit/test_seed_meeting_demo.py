from scripts.seed_meeting_demo import build_parser, marker


def test_demo_seed_requires_explicit_scope_and_defaults_to_dry_run():
    args = build_parser().parse_args(["--account-id", "acc_1", "--club-id", "clb_1"])
    assert args.dry_run is False  # no mode is also dry-run
    assert args.apply is False
    assert args.rollback is False
    assert args.manager_account_id is None
    assert marker(args.demo_key) == "[DEMO:meeting-beta-1]"


def test_demo_seed_accepts_second_operator_for_golden_path():
    args = build_parser().parse_args(
        [
            "--account-id",
            "acc_owner",
            "--manager-account-id",
            "acc_manager",
            "--club-id",
            "clb_1",
        ]
    )
    assert args.manager_account_id == "acc_manager"


def test_demo_seed_modes_are_mutually_exclusive():
    parser = build_parser()
    try:
        parser.parse_args(["--account-id", "acc_1", "--club-id", "clb_1", "--dry-run", "--apply"])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("--apply and --rollback must not be combined")
