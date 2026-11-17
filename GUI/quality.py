from decimal import Decimal, InvalidOperation
import re


QUALITY_CATEGORIES = (
    "GOOD",
    "MOLDY",
    "SLATY",
    "GERMINATED",
    "INSECT-DAMAGED",
    "FLAT",
    "BROKEN",
    "DOUBLE",
)


def pns_grade_from_weighted_count(
    bean_count: object,
    weight_grams: object,
) -> str:
    try:
        count = Decimal(str(bean_count))
        weight = Decimal(str(weight_grams))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    if (
        not count.is_finite()
        or count < 0
        or count != count.to_integral_value()
        or not weight.is_finite()
        or weight <= 0
    ):
        return ""

    ratio = count / weight
    if ratio < Decimal("1.01"):
        return "A"
    if ratio <= Decimal("1.20"):
        return "B"
    return "C"


def normalize_quality_category(raw_name: object) -> str | None:
    normalized = re.sub(
        r"\s*\([^)]*\)\s*$",
        "",
        str(raw_name).strip().upper(),
    )
    normalized = re.sub(r"[\s_]+", "-", normalized)
    normalized = re.sub(r"-BEANS?$", "", normalized)
    if normalized == "INSECT-DAMAGE":
        normalized = "INSECT-DAMAGED"
    return normalized if normalized in QUALITY_CATEGORIES else None


def is_foreign_object_category(raw_name: object) -> bool:
    normalized = re.sub(
        r"\s*\([^)]*\)\s*$",
        "",
        str(raw_name).strip().upper(),
    )
    normalized = re.sub(r"[\s_]+", "-", normalized)
    return normalized == "FOREIGN-OBJECT"
