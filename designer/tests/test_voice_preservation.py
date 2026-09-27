import pytest

from designer.voice_preservation import preservation_violations


@pytest.mark.parametrize(('original', 'rewritten'), [
    ('Margin: +20%.', 'Margin: -20%.'),
    ('Margin: \u221220%.', 'Margin: 20%.'),
    ('Margin: 20%.', 'Margin: 20\u2030.'),
    ('Rate: 1.25%.', 'Rate: 125%.'),
    ('Mass: 1 200 kg.', 'Mass: 1.200 kg.'),
    ('Mass: 20 kg.', 'Mass: 20 lb.'),
    ('Speed: 20 km/h.', 'Speed: 20 km/s.'),
    ('Speed: 20 km / h.', 'Speed: 20 km / s.'),
    ('Rate: 20 kg per second.', 'Rate: 20 kg per minute.'),
    ('Power: 20 mW.', 'Power: 20 MW.'),
    ('Current: 20 A.', 'Current: 20.'),
    ('Width: 20 in.', 'Width: 20.'),
    ('Width: 20".', 'Width: 20.'),
    ('Delay: 20 \u0441.', 'Delay: 20.'),
    ('Limit: <20.', 'Limit: >20.'),
    ('Area: 20 m2.', 'Area: 20 m3.'),
    ('Price: $20.', 'Price: \u20ac20.'),
    ('Price: 20 million USD.', 'Price: 20 billion USD.'),
    ('Price: 20 million USD.', 'Price: 20 million EUR.'),
    ('Revenue: 20%, costs: 10%.', 'Revenue: 10%, costs: 20%.'),
    ('Revenue grew 20%; costs grew 10%.', 'Revenue grew 10%; costs grew 20%.'),
    ('20% annual revenue; 10% annual costs.', '10% annual revenue; 20% annual costs.'),
    ('Price: 20 \u043c\u043b\u043d. \u0440\u0443\u0431.',
     'Price: 20 \u043c\u043b\u043d. \u0434\u043e\u043b\u043b.'),
    ('20 users; 10 admins.', '10 users; 20 admins.'),
    ('Revenue: 20%; costs: 20%.', 'Revenue: 20%.'),
    ('No numeric claim.', 'Growth: 20%.'),
])
def test_numeric_fact_changes_are_rejected(original, rewritten):
    assert preservation_violations(original, rewritten, preserve_numbers=True) == ['preserve_numbers']


@pytest.mark.parametrize(('original', 'rewritten'), [
    ('Launch: 2024.', 'Launch soon.'),
    ('Launch: 2024-05-12.', 'Launch: 2024-12-05.'),
    ('Launch: 12.05.2024.', 'Launch: 12.05.2025.'),
    ('Launch: 12/05/24.', 'Launch: 05/12/24.'),
    ('Launch: September 12, 2024.', 'Launch: September 12.'),
    ('Launch: 12 September 2024.', 'Launch: 12 September 2025.'),
    ('Launch: September 2024.', 'Launch: October 2024.'),
    ('Launch: September.', 'Launch: October.'),
    ('Launch: 12 \u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f 2024.',
     'Launch: 12 \u043e\u043a\u0442\u044f\u0431\u0440\u044f 2024.'),
    ('Launch: 2024; closure: 2025.', 'Launch: 2025; closure: 2024.'),
])
def test_calendar_changes_are_rejected(original, rewritten):
    assert preservation_violations(original, rewritten, preserve_dates=True) == ['preserve_dates']


@pytest.mark.parametrize(('original', 'rewritten'), [
    ('Revenue was +20% in 2024. The team celebrated.', 'Revenue: +20% in 2024.'),
    ('Launch: 12 September 2024. This is the plan.', 'Launch: 12 September 2024.'),
    ('Mass: 1\u00a0200 kg. This is heavy.', 'Mass: 1 200 kg.'),
    ('Revenue: 20%. Costs: 10%.', 'Costs: 10%. Revenue: 20%.'),
])
def test_same_facts_allow_unrelated_prose_changes(original, rewritten):
    assert preservation_violations(original, rewritten, preserve_numbers=True, preserve_dates=True) == []


def test_date_constraint_does_not_require_unrelated_quantities():
    assert preservation_violations('Launch: 2024. Mass: 20 kg.', 'Launch: 2024. Mass: 10 kg.',
                                   preserve_dates=True) == []


def test_absent_constraints_do_not_change_legacy_behavior():
    assert preservation_violations('Launch: 2024. Margin: +20%.', 'A shorter summary.') == []


def test_long_whitespace_is_safe_to_scan():
    assert preservation_violations(' ' * 12000, 'A summary.', preserve_numbers=True) == []
