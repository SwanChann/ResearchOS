from concurrent.futures import ThreadPoolExecutor

from researchflow.ids import allocate_id, validate_id


def test_id_allocation_is_unique_and_stable(rf_env):
    with ThreadPoolExecutor(max_workers=4) as executor:
        values = list(executor.map(lambda _: allocate_id(rf_env["home"], "EXP"), range(12)))
    assert len(values) == len(set(values)) == 12
    assert sorted(values) == [f"EXP-{number:04d}" for number in range(1, 13)]
    assert validate_id("RUN-000001", "RUN")
    assert not validate_id("EXP-1", "EXP")

