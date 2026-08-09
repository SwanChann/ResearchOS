import pytest

from researchflow.errors import ValidationError
from researchflow.schema import validate_record


def test_schema_error_is_user_facing():
    with pytest.raises(ValidationError, match="Invalid observation at id"):
        validate_record("observation", {
            "id": "bad", "created": "now", "type": "project_observation",
            "title": "x", "evidence": {}, "confidence": "medium",
        })
