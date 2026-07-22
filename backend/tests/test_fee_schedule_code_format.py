from app.services.fee_schedule.code_format import classify_code_format, is_ama_licensed_format
from app.services.fee_schedule.types import CodeFormat


def test_cpt_category_i_five_digits():
    assert classify_code_format("76705") == CodeFormat.CPT_CATEGORY_I
    assert is_ama_licensed_format(CodeFormat.CPT_CATEGORY_I) is True


def test_cpt_category_ii_iii_four_digits_plus_letter():
    assert classify_code_format("0001T") == CodeFormat.CPT_CATEGORY_II_III
    assert classify_code_format("0001F") == CodeFormat.CPT_CATEGORY_II_III
    assert is_ama_licensed_format(CodeFormat.CPT_CATEGORY_II_III) is True


def test_hcpcs_level_ii_letter_plus_four_digits():
    assert classify_code_format("A4238") == CodeFormat.HCPCS_LEVEL_II
    assert is_ama_licensed_format(CodeFormat.HCPCS_LEVEL_II) is False


def test_unrecognized_format():
    assert classify_code_format("hello") == CodeFormat.UNKNOWN
    assert classify_code_format("123") == CodeFormat.UNKNOWN
    assert classify_code_format("AB1234") == CodeFormat.UNKNOWN


def test_lowercase_input_normalized():
    assert classify_code_format("a4238") == CodeFormat.HCPCS_LEVEL_II
