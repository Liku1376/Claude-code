import json
import os
import random
from datetime import date, timedelta

import pytest

from roster_tool import export
from roster_tool.model import (
    COMP_OFF,
    HOLIDAY_OFF,
    LEAVE,
    LONG_LEAVE,
    MORNING,
    NIGHT,
    WEEK_OFF,
    RosterConfig,
    empty_config_dict,
)
from roster_tool.scheduler import generate
from roster_tool.validator import ERROR, WARNING, validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def team(non_sme=5, sme=2):
    return [{"name": f"N{i}", "designation": "Engineer", "sme": False} for i in range(non_sme)] + [
        {"name": f"S{i}", "designation": "SME", "sme": True} for i in range(sme)
    ]


def config(**overrides):
    d = empty_config_dict(2026, 10)
    d["engineers"] = team()
    d["attempts"] = 40
    d["seed"] = "1"
    d.update(overrides)
    return RosterConfig.from_dict(d)


def errors(issues):
    return [i for i in issues if i.severity == ERROR]


def assert_mandatory_rules(roster):
    cfg = roster.config
    sme = {e.name for e in cfg.engineers if e.is_sme}
    for d in cfg.days:
        dtype = cfg.day_type(d)
        if dtype == "Working":
            assert roster.on_shift(d, MORNING), f"no morning on {d}"
            assert roster.on_shift(d, NIGHT), f"no night on {d}"
        for n in cfg.engineer_names:
            code = roster.code(n, d)
            if code == COMP_OFF:
                assert not cfg.is_off_day(d), f"comp off on off day {d}"
            if code == NIGHT:
                co = cfg.comp_off_day(d)
                if co <= cfg.days[-1]:
                    assert roster.code(n, co) == COMP_OFF
                rest = d + timedelta(days=1)
                while rest < co and rest <= cfg.days[-1]:
                    assert roster.code(n, rest) not in (MORNING, NIGHT, "E")
                    rest += timedelta(days=1)
        p = roster.primary[d]
        assert p not in sme
        assert roster.code(p, d) not in (MORNING, NIGHT, COMP_OFF, LEAVE, LONG_LEAVE)
        if cfg.is_off_day(d):
            assert d not in roster.secondary
        else:
            assert roster.secondary[d] in sme


def test_sample_config_meets_all_rules():
    with open(os.path.join(ROOT, "examples", "sample_config.json")) as fh:
        cfg = RosterConfig.from_dict(json.load(fh))
    roster, issues = generate(cfg)
    assert errors(issues) == []
    assert [i for i in issues if i.severity == WARNING] == []
    assert_mandatory_rules(roster)


def test_weekends_holidays_and_freeze():
    cfg = config(
        holidays=[{"date": "2026-10-02", "name": "Holiday"}],
        freeze_periods=[{"start": "26", "end": "30"}],
    )
    roster, issues = generate(cfg)
    assert errors(issues) == []
    assert_mandatory_rules(roster)
    assert cfg.day_type(date(2026, 10, 2)) == "Holiday"
    assert cfg.day_type(date(2026, 10, 3)) == "Weekend"
    assert cfg.day_type(date(2026, 10, 27)) == "Freeze"
    # Holidays/weekends: nobody works by default (except comp offs/leave).
    assert all(roster.code(n, date(2026, 10, 2)) in (HOLIDAY_OFF, COMP_OFF) for n in cfg.engineer_names)
    assert all(roster.code(n, date(2026, 10, 4)) == WEEK_OFF for n in cfg.engineer_names)
    # Freeze days are not forced to have a night shift.
    assert not roster.on_shift(date(2026, 10, 27), NIGHT)


def test_leave_long_leave_and_requirements_honoured():
    cfg = config(
        leaves=[{"engineer": "N0", "start": "5", "end": "6"}],
        long_leaves=[{"engineer": "N1", "start": "12", "end": "23"}],
        requirements=[
            {"engineer": "N2", "start": "1", "end": "9", "shift": "Morning", "mode": "Must"},
            {"engineer": "N3", "start": "1", "end": "31", "shift": "Night", "mode": "Avoid"},
        ],
    )
    roster, issues = generate(cfg)
    assert errors(issues) == []
    assert roster.code("N0", date(2026, 10, 5)) == LEAVE
    assert all(roster.code("N1", date(2026, 10, d)) == LONG_LEAVE for d in range(12, 24))
    assert all(roster.code("N2", d) == MORNING for d in cfg.days[:9] if not cfg.is_off_day(d))
    assert all(roster.code("N3", d) != NIGHT for d in cfg.days)


def test_oncall_override_used():
    cfg = config(oncall=[{"date": "7", "primary": "N4", "secondary": "S1"}])
    roster, issues = generate(cfg)
    assert errors(issues) == []
    assert roster.primary[date(2026, 10, 7)] == "N4"
    assert roster.secondary[date(2026, 10, 7)] == "S1"


def test_oncall_is_rotated_fairly():
    cfg = config()
    roster, _ = generate(cfg)
    primaries = [roster.counts(f"N{i}")["Primary"] for i in range(5)]
    secondaries = [roster.counts(f"S{i}")["Secondary"] for i in range(2)]
    assert max(primaries) - min(primaries) <= 2
    assert max(secondaries) - min(secondaries) <= 1


def test_validator_flags_manual_violations():
    cfg = config()
    roster, _ = generate(cfg)
    d = date(2026, 10, 1)
    night = roster.on_shift(d, NIGHT)[0]
    roster.grid[night][d + timedelta(days=1)] = MORNING  # no comp off
    roster.primary[d] = "S0"  # SME as primary
    msgs = [i.message for i in errors(validate(roster))]
    assert any("comp off is due" in m for m in msgs)
    assert any("is an SME" in m for m in msgs)


def test_infeasible_inputs_are_reported_not_crashing():
    # Only SMEs -> no primary on-call possible.
    cfg = config(engineers=team(non_sme=0, sme=2))
    roster, issues = generate(cfg)
    assert any("No primary on-call" in i.message for i in errors(issues))


def test_bad_input_raises_readable_error():
    with pytest.raises(ValueError, match="unknown engineer"):
        config(leaves=[{"engineer": "Nobody", "start": "1"}])
    with pytest.raises(ValueError, match="invalid date"):
        config(holidays=[{"date": "tomorrow"}])


@pytest.mark.parametrize("seed", range(15))
def test_random_scenarios_keep_mandatory_rules(seed):
    rng = random.Random(seed)
    non_sme, sme = rng.randint(5, 9), rng.randint(2, 4)
    names = [f"N{i}" for i in range(non_sme)]
    leaves = []
    for _ in range(rng.randint(0, 4)):
        start = rng.randint(1, 28)
        leaves.append({"engineer": rng.choice(names), "start": str(start), "end": str(start + rng.randint(0, 2))})
    cfg = config(
        engineers=team(non_sme, sme),
        leaves=leaves,
        holidays=[{"date": str(rng.randint(1, 31))}],
        freeze_periods=[{"start": "24", "end": "27"}] if seed % 2 else [],
        seed=str(seed),
    )
    roster, issues = generate(cfg)
    assert errors(issues) == []
    assert_mandatory_rules(roster)


def test_exports(tmp_path):
    cfg = config()
    roster, issues = generate(cfg)
    csv_path = tmp_path / "r.csv"
    export.to_csv(roster, str(csv_path))
    text = csv_path.read_text()
    assert "Primary on-call" in text and "N0" in text
    pytest.importorskip("openpyxl")
    xlsx = tmp_path / "r.xlsx"
    export.to_excel(roster, str(xlsx), issues)
    assert xlsx.stat().st_size > 0


def test_friday_night_comp_off_moves_to_monday():
    cfg = config()
    roster, issues = generate(cfg)
    assert errors(issues) == []
    fri = date(2026, 10, 9)
    worker = roster.on_shift(fri, NIGHT)[0]
    assert roster.code(worker, date(2026, 10, 10)) == WEEK_OFF
    assert roster.code(worker, date(2026, 10, 11)) == WEEK_OFF
    assert roster.code(worker, date(2026, 10, 12)) == COMP_OFF
    # Resting engineers are not put on call before their comp off.
    assert roster.primary[date(2026, 10, 10)] != worker


def test_night_before_holiday_comp_off_skips_holiday():
    # Thu 1 Oct night, Fri 2 Oct holiday, weekend -> comp off Mon 5 Oct.
    cfg = config(holidays=[{"date": "2", "name": "Holiday"}])
    assert cfg.comp_off_day(date(2026, 10, 1)) == date(2026, 10, 5)
    roster, issues = generate(cfg)
    assert errors(issues) == []
    worker = roster.on_shift(date(2026, 10, 1), NIGHT)[0]
    assert roster.code(worker, date(2026, 10, 2)) == HOLIDAY_OFF
    assert roster.code(worker, date(2026, 10, 5)) == COMP_OFF


def test_comp_off_on_weekend_is_flagged():
    cfg = config()
    roster, _ = generate(cfg)
    roster.grid["N0"][date(2026, 10, 10)] = COMP_OFF  # a Saturday
    msgs = [i.message for i in errors(validate(roster))]
    assert any("comp offs must be on working days" in m for m in msgs)


# ---- v1.2 features -----------------------------------------------------------
from roster_tool import ics, storage  # noqa: E402
from roster_tool.model import Locks  # noqa: E402
from roster_tool.validator import INFO, precheck, preference_stats  # noqa: E402


def test_locked_cells_survive_regenerate():
    cfg = config()
    d = date(2026, 10, 14)
    locks = Locks({("N0", d): NIGHT, ("N1", date(2026, 10, 6)): LEAVE}, {date(2026, 10, 7): "N2"})
    roster, issues = generate(cfg, locks)
    assert roster.code("N0", d) == NIGHT
    assert roster.code("N0", date(2026, 10, 15)) == COMP_OFF
    assert roster.code("N1", date(2026, 10, 6)) == LEAVE
    assert roster.primary[date(2026, 10, 7)] == "N2"
    assert errors(issues) == []
    assert roster.locks.cells[("N0", d)] == NIGHT


def test_regenerate_against_published_changes_little():
    cfg = config()
    published, _ = generate(cfg)
    cfg2 = config(leaves=[{"engineer": "N0", "start": "20", "end": "21"}])
    roster, issues = generate(cfg2, baseline=published)
    assert errors(issues) == []
    changes = storage.diff(published, roster)
    free, _ = generate(cfg2)
    assert len(changes) < len(storage.diff(published, free))
    assert len(changes) <= 12


def test_preferences_are_mostly_met():
    cfg = config(requirements=[{"engineer": "N0", "start": "1", "end": "31", "shift": "Morning", "mode": "Prefer"}])
    roster, issues = generate(cfg)
    assert errors(issues) == []
    met, requested = preference_stats(roster)
    assert requested > 0 and met / requested >= 0.6
    assert any(i.severity == INFO and "preferences met" in i.message for i in issues)


def test_carry_over_comp_off_and_fairness():
    oct_cfg = config()
    oct_roster, _ = generate(oct_cfg)
    # Force a night on Fri 30 Oct so its comp off falls on Mon 2 Nov.
    oct_roster.grid["N0"][date(2026, 10, 30)] = NIGHT
    carry = storage.carry_over_from(oct_roster)
    assert {"engineer": "N0", "date": "2026-10-30"} in carry["nights"]
    nov = RosterConfig.from_dict({**empty_config_dict(2026, 11), "engineers": team(), "attempts": 40, "seed": "1", "carry_over": carry})
    assert nov.carried_comp_offs()["N0"] == date(2026, 11, 2)
    roster, issues = generate(nov)
    assert errors(issues) == []
    assert roster.code("N0", date(2026, 11, 2)) == COMP_OFF
    assert roster.primary[date(2026, 11, 1)] != "N0"
    totals = [roster.total_counts(n)[NIGHT] for n in nov.engineer_names]
    assert max(totals) - min(totals) <= 2


def test_precheck_flags_understaffed_days():
    everyone_off = [{"engineer": f"N{i}", "start": "14"} for i in range(5)]
    cfg = config(leaves=everyone_off)
    msgs = [i.message for i in precheck(cfg) if i.day == date(2026, 10, 14)]
    assert any("primary on-call" in m for m in msgs)
    assert precheck(config()) == []


def test_swap_moves_duties_and_locks():
    cfg = config()
    roster, _ = generate(cfg)
    d = date(2026, 10, 7)
    p = roster.primary[d]
    other = next(n for n in cfg.engineer_names if n != p and not cfg.engineer(n).is_sme)
    new = storage.swap(roster, p, other, d)
    assert new.primary[d] == other
    assert new.code(p, d) == roster.code(other, d)
    assert (p, d) in new.locks.cells and new.locks.primary[d] == other
    assert roster.primary[d] == p  # original untouched
    whos = {c.who for c in storage.diff(roster, new)}
    assert "Primary on-call" in whos


def test_roster_file_roundtrip(tmp_path):
    inputs = {**empty_config_dict(2026, 10), "engineers": team(), "attempts": 10, "seed": "3"}
    cfg = RosterConfig.from_dict(inputs)
    roster, _ = generate(cfg, Locks({("N0", date(2026, 10, 5)): MORNING}))
    published = roster.copy()
    roster.grid["N1"][date(2026, 10, 6)] = LEAVE
    path = tmp_path / "oct.json"
    storage.save_roster_file(str(path), inputs, roster, published, "today")
    rf = storage.load_roster_file(str(path))
    assert rf.roster.grid == roster.grid
    assert rf.roster.primary == roster.primary
    assert rf.roster.locks.cells == roster.locks.cells
    assert rf.published.grid == published.grid
    assert len(storage.diff(rf.published, rf.roster)) == 1


def test_ics_export(tmp_path):
    cfg = config()
    roster, _ = generate(cfg)
    text = ics.build_calendar(roster, "N0")
    assert text.startswith("BEGIN:VCALENDAR") and text.rstrip().endswith("END:VCALENDAR")
    assert text.count("BEGIN:VEVENT") == text.count("END:VEVENT") > 0
    night = next(d for d in roster.days if roster.code("N0", d) == NIGHT)
    assert f"DTSTART:{night:%Y%m%d}T220000" in text
    assert f"DTEND:{night + timedelta(days=1):%Y%m%d}T060000" in text
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    paths = ics.export_all(roster, str(tmp_path))
    assert len(paths) == len(cfg.engineers) + 1


def test_swapping_a_night_moves_its_comp_off():
    cfg = config()
    roster, _ = generate(cfg)
    d = next(day for day in roster.days if not cfg.is_off_day(day) and roster.on_shift(day, NIGHT)
             and cfg.comp_off_day(day) <= roster.days[-1])
    worker = roster.on_shift(d, NIGHT)[0]
    co = cfg.comp_off_day(d)
    other = next(n for n in cfg.engineer_names
                 if roster.code(n, d) in (MORNING, "E") and roster.code(n, co) in (MORNING, "E")
                 and n not in (roster.primary.get(d), roster.secondary.get(d)))
    new = storage.swap(roster, worker, other, d)
    assert new.code(other, d) == NIGHT and new.code(other, co) == COMP_OFF
    assert new.code(worker, co) == roster.code(other, co)
    comp_off_errors = [i for i in errors(validate(new)) if "comp off" in i.message]
    assert comp_off_errors == []


def test_excel_export_survives_control_characters(tmp_path):
    pytest.importorskip("openpyxl")
    cfg = config()
    roster, issues = generate(cfg)
    # A control char pasted into a non-key field must not break the export.
    cfg.engineers[0].designation = "Senior\x07Engineer"
    cfg.engineers[1].name  # touch to be explicit
    path = tmp_path / "r.xlsx"
    export.to_excel(roster, str(path), issues)   # must not raise
    import openpyxl
    wb = openpyxl.load_workbook(str(path))
    assert wb.active["A1"].value == "Engineer"
