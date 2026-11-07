"""Shared synthetic dictionary text for the LLM tests."""

DICT_MD = """# Data dictionary

## health

### health / ed_visits

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `visit_id` | record_key | RECORD_ID |  | Visit identifier |
| `los_minutes` | sensitive_attribute | HEALTH_DATA | yes | Length of stay in minutes |

### health / lab_results

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `lab_id` | record_key | RECORD_ID |  | Lab result identifier |

## other

### other / things

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `thing` | non_sensitive | CATEGORY |  | A thing |
"""

